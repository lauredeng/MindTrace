"""Real file parsing and offline model contracts for the teacher intake."""
from copy import deepcopy
import io
import json
import shutil
from types import SimpleNamespace

from PIL import Image, ImageDraw
import pytest

from core import ai, classroom, collaboration, education, presentation, product, uploads
from core.limits import UsageLimitError


SIZE = 20 * 1024**2


def pictures(student, count):
    pages=[]
    for page in range(count):
        im=Image.new('RGB',(72,60),'white')
        draw=ImageDraw.Draw(im)
        draw.rectangle((3,3,21+page,22),fill=(student%255,page*30%255,50))
        draw.text((4,34),f'{student:03d}/{page:02d}',fill='black')
        pages.append(im)
    return pages


def uploaded(name, key, data):
    return SimpleNamespace(name=name,file_id=str(key),size=len(data),getvalue=lambda:data)


def pdf_file(student, count, name=None):
    pages=pictures(student,count)
    out=io.BytesIO()
    pages[0].save(out,format='PDF',save_all=True,append_images=pages[1:])
    return uploaded(name or f'S{student:03d}_homework.pdf',student,out.getvalue())


def photo_files(count):
    files=[]
    for index,page in enumerate(pictures(1,count)):
        out=io.BytesIO();page.save(out,format='PNG')
        files.append(uploaded(f'photo-{index+1}.png',index,out.getvalue()))
    return files


def fixture_page(*, student='', question='题目 1：求圆的半径。', answer='2', reference=''):
    return {'transcription':'模型替身转写','warnings':[],'identity_candidates':[student] if student else [],
            'records':[{'student_id':'','question_no':'1','question':question,'question_type':'填空题',
                        'steps':[],'answer':answer,'question_ref':reference,
                        'answer_status':'answered' if answer else 'continued'}]}


def quick(prompt,raw,**kwargs):
    assert kwargs['purpose']=='quick_grading'
    assert json.loads(raw)['answer']=='2'
    return {'verdict':'correct','process_checked':False,'basis':'模型替身：答案正确。'}


@pytest.mark.skipif(not shutil.which('pdfinfo') or not shutil.which('pdftoppm'),reason='Poppler required')
@pytest.mark.parametrize(('count','page_count'),[(40,3),(100,1)])
def test_class_pdf_files_render_in_order_and_stay_with_their_owner(count,page_count,tmp_path):
    docs=uploads.upload_documents([pdf_file(i,page_count) for i in range(1,count+1)],'pdf',SIZE)
    assert len(docs)==count
    states={};seen=[]

    def model(prompt,user,**kwargs):
        assert kwargs['purpose']=='ocr'
        index=len(seen)
        page=index%page_count
        seen.append(user[1]['image_url']['url'])
        student=f'S{index//page_count+1:03d}'
        if not page:
            assert '目录：' not in user[0]['text']
            return fixture_page(student=student,answer='' if page_count>1 else '2')
        catalog=json.loads(user[0]['text'].split('目录：')[1])
        return fixture_page(question='',reference=next(iter(catalog)),answer='2')

    for _ in range((count*page_count+19)//20+1):
        if not uploads.process_pages(docs,list(docs),states,model,mode='pdf',limit_bytes=SIZE):break
    materials,rows=uploads.assemble_materials(docs,list(docs),states,mode='pdf')
    assert len(seen)==count*page_count and len(rows)==len(materials)==count
    for document,material,row in zip(docs.values(),materials,rows):
        assert row['student_id']=='PAPER-'+document['file_id']==material['student_id']
        assert row['source_pages']==list(range(1,page_count+1))
        assert {p['file_id'] for p in material['pages']}=={document['file_id']}
        assert all(p['recognized_records'] for p in material['pages'])
        classroom.attach_image(document['data'],tmp_path/'originals')
        assert classroom.read_image(document['file_id'],tmp_path/'originals')==document['data']
    w=classroom.new_workspace()
    batch=product.create_batch(w,'整班作业',rows,materials=materials,grading_policy=product.CLASSROOM_POLICY)
    product.run_batch(w,batch['id'],quick)
    assert presentation.batch_summary(w,batch['id'],automatic=True)['correctness']==1
    assert 'materials' not in collaboration.student_view(w,rows[0]['student_id'])['batches'][0]
    with pytest.raises(ValueError,match='已保存'):
        product.create_batch(w,'整班作业',[dict(row,answer='3') for row in rows],materials=materials)
    bad=deepcopy(w)
    bad['batches'][0]['materials'][1]['pages'][0]['file_id']=materials[0]['pages'][0]['file_id']
    with pytest.raises(ValueError):classroom.validate_workspace(bad)


def test_single_student_five_photos_in_adjusted_order_retry_without_repeating_success():
    docs=uploads.upload_documents(photo_files(5),'photos',SIZE)
    order=['1','0','2','3','4']
    states={};calls=[]
    def model(prompt,user,**kwargs):
        calls.append(user[1]['image_url']['url'])
        if len(calls)==3:raise UsageLimitError('暂时限流')
        return fixture_page()
    assert '限流' in uploads.process_pages(docs,order,states,model,mode='photos',limit_bytes=SIZE)
    assert not uploads.process_pages(docs,order,states,model,mode='photos',limit_bytes=SIZE)
    assert len(calls)==6 and calls[2]==calls[3] and len(set(calls))==5
    materials,rows=uploads.assemble_materials(docs,order,states,mode='photos')
    assert len(materials)==len(rows)==1
    assert rows[0]['student_id'].startswith('PAPER-') and rows[0]['source_pages']==[1,2,3,4,5]
    assert [p['filename'] for p in materials[0]['pages']]==[docs[k]['name'] for k in order]
    w=classroom.new_workspace()
    batch=product.create_batch(w,'照片作业',rows,materials=materials,grading_policy=product.CLASSROOM_POLICY)
    product.run_batch(w,batch['id'],quick)
    assert presentation.batch_summary(w,batch['id'],automatic=True)['submitted_students']==1


def test_only_duplicate_file_content_is_rejected():
    one=pdf_file(1,1,'S01.pdf')
    two=pdf_file(2,1,'S01_第二份.pdf')
    copy=uploaded('S02.pdf','copy',one.getvalue())
    docs=uploads.upload_documents([one,two,copy],'pdf',SIZE)
    assert uploads.duplicate_files(docs)=={'1','copy'}
    files=[uploaded('S01.pdf',i,one.getvalue()) for i in range(101)]
    with pytest.raises(ValueError,match='100'):uploads.upload_documents(files,'pdf',SIZE)


def test_retry_only_failed_pdf_without_reprocessing_other_files(monkeypatch):
    files=[pdf_file(i,1) for i in range(1,4)]
    docs=uploads.upload_documents(files,'pdf',SIZE)
    images=[photo.getvalue() for photo in photo_files(3)]
    monkeypatch.setattr(uploads,'render_document',lambda doc,*_: [images[int(doc['name'][1:4])-1]])
    states={};calls=[]
    def model(prompt,user,**kwargs):
        calls.append(user[1]['image_url']['url'])
        if len(calls)==2:raise RuntimeError('模拟单个 PDF 识别失败')
        return fixture_page()
    uploads.process_pages(docs,list(docs),states,model,mode='pdf',limit_bytes=SIZE)
    failed=states[docs['2']['file_id']]
    assert '失败' in failed['error'] and len(calls)==3
    uploads.process_pages(docs,['2'],states,model,mode='pdf',limit_bytes=SIZE)
    assert len(calls)==4 and calls[3]==calls[1] and not failed['error']


def test_truncated_page_uses_two_regions_and_resumes_only_the_unfinished_region():
    docs=uploads.upload_documents(photo_files(1),'photos',SIZE)
    states={};phases=[]
    def model(prompt,user,**kwargs):
        message=user[0]['text']
        if '上半部分' in message:
            payload=fixture_page(answer='')
            payload['records'][0]['steps']=['第一步','重叠步骤']
            payload.pop('transcription')
            return payload
        if '下半部分' in message:
            if len(phases)==3:raise UsageLimitError('暂时限流')
            catalog=json.loads(message.split('目录：')[1])
            payload=fixture_page(question='',reference=next(iter(catalog)))
            payload['records'][0]['steps']=['重叠步骤','最后一步']
            return payload
        raise ai.OutputTruncatedError('输出过长')

    def progress(name,page,total,region):
        phases.append(region)

    options=dict(mode='photos',limit_bytes=SIZE,progress=progress)
    assert '限流' in uploads.process_pages(docs,['0'],states,model,**options)
    assert not uploads.process_pages(docs,['0'],states,model,**options)
    assert phases==[None,'上半部分','下半部分','下半部分']
    materials,rows=uploads.assemble_materials(docs,['0'],states,mode='photos')
    assert rows[0]['steps']=='第一步\n重叠步骤\n最后一步'
    assert rows[0]['answer']=='2' and rows[0]['source_pages']==[1]
    assert materials[0]['pages'][0]['original_image']==docs['0']['file_id']


@pytest.mark.parametrize('failures',[1,2])
def test_malformed_json_retries_only_the_failed_region(monkeypatch,failures):
    docs=uploads.upload_documents([pdf_file(8,1,'student_A.pdf')],'pdf',SIZE)
    images=[item.getvalue() for item in photo_files(1)]
    monkeypatch.setattr(uploads,'render_document',lambda *args:images)
    calls=[]
    def model(prompt,user,**kwargs):
        message=user[0]['text']
        if '上半部分' in message:
            calls.append('top')
            return fixture_page(answer='')
        if '下半部分' in message:
            calls.append('strict' if '正确转义' in prompt else 'bottom')
            if len(calls)<=2+failures:
                raise ai.InvalidModelJSON('模拟格式异常')
            return {'records':[],'answers':[{'question_no':'1','answer':'2','answer_status':'answered'}]}
        calls.append('full')
        raise ai.OutputTruncatedError('模拟截断')
    states={}
    uploads.process_pages(docs,['8'],states,model,mode='pdf',limit_bytes=SIZE)
    assert calls==['full','top','bottom','strict']
    state=states[docs['8']['file_id']]
    if failures==2:
        assert '已保留成功的部分' in state['error']
        uploads.process_pages(docs,['8'],states,model,mode='pdf',limit_bytes=SIZE)
        assert calls==['full','top','bottom','strict','bottom']
    assert not state['error']
    _,rows=uploads.assemble_materials(docs,['8'],states,mode='pdf')
    assert rows[0]['answer']=='2' and rows[0]['source_pages']==[1]


def test_document_matches_standalone_answers_and_only_counts_whole_document_blanks(monkeypatch):
    docs=uploads.upload_documents([pdf_file(8,3,'student_A.pdf'),pdf_file(9,3,'student_B.pdf')],'pdf',SIZE)
    images=[item.getvalue() for item in photo_files(6)]
    monkeypatch.setattr(uploads,'render_document',lambda doc,*_:images[:3] if doc['name']=='student_A.pdf' else images[3:])
    question=lambda number,stem,**fields:dict(question_no=number,question=stem,question_type='填空题',
                                             answer_status='not_on_page',steps=[],**fields)
    answers=lambda **fields:dict(steps=[],answer_status='answered',**fields)
    payloads=[
        {'records':[question('1','求半径。'),question('2','求周长。'),
                    question('3','求面积。选项 A、B',stem_status='continued'),
                    question('4','求直径。')]},
        {'records':[question('3','选项 C、D',stem_status='fragment')]},
        {'records':[],'answers':[answers(question_no='第1题',answer='2'),answers(question_no='3',answer='2'),
                                 {'question_no':'4','answer_status':'unreadable'}]},
    ]
    replies=iter(payloads+payloads[:2]+[dict(payloads[2],answers=payloads[2]['answers'][1:])])
    states={}
    uploads.process_pages(docs,list(docs),states,lambda *a,**k:next(replies),mode='pdf',limit_bytes=SIZE)
    materials,rows=uploads.assemble_materials(docs,list(docs),states,mode='pdf')
    assert materials[0]['student_id']!=materials[1]['student_id']
    assert rows[0]['answer']=='2' and rows[0]['source_pages']==[1,3]
    assert rows[1]['answer']=='' and rows[1]['source_pages']==[1]
    assert rows[2]['source_pages']==[1,2,3] and rows[2]['question'].endswith('选项 C、D')
    assert rows[3]['answer']=='[无法辨认]' and rows[4]['answer']==''
    w=classroom.new_workspace()
    batch=product.create_batch(w,'整卷跨页',rows,materials=materials,grading_policy=product.CLASSROOM_POLICY)
    product.run_batch(w,batch['id'],quick)
    heat= presentation.heatmap_rows(w,batch['id'],automatic=True)
    assert [(r['correct'],r['errors'],r['unreadable']) for r in heat]==[(1,1,0),(0,2,0),(2,0,0),(0,0,2)]
    states[docs['8']['file_id']]['drafts'][2]['answers'][0]['question_no']='99'
    with pytest.raises(ValueError,match='未找到唯一对应题目'):
        uploads.assemble_materials(docs,list(docs),states,mode='pdf')


def test_shared_stem_at_page_end_is_used_for_next_page_subquestions(monkeypatch):
    docs=uploads.upload_documents([pdf_file(8,3,'student_A.pdf')],'pdf',SIZE)
    images=[item.getvalue() for item in photo_files(3)]
    monkeypatch.setattr(uploads,'render_document',lambda *args:images)
    def stem(number,content,**fields):
        return dict(question_no=number,question=content,question_type='解答题',steps=[],answer_status='not_on_page',**fields)
    pages=iter([
        {'records':[stem('17','公共条件：直线 AB 垂直平面 P。',stem_status='shared')]},
        {'records':[stem('（1）','证明 AC 垂直 AB。'),stem('（2）','求角度。')]},
        {'records':[],'answers':[{'question_no':'17.1','steps':['因为…'], 'answer_status':'answered'}]},
    ])
    states={}
    uploads.process_pages(docs,['8'],states,lambda *a,**k:next(pages),mode='pdf',limit_bytes=SIZE)
    _,rows=uploads.assemble_materials(docs,['8'],states,mode='pdf')
    assert [row['question_no'] for row in rows]==['17(1)','17(2)']
    assert all('公共条件' in row['question'] for row in rows)
    assert rows[0]['source_pages']==[1,2,3] and rows[1]['source_pages']==[1,2]
    assert product.is_blank(education.normalize_submission(rows[1],allow_unanswered=True))


def test_identical_pdf_question_pages_are_reused_without_sharing_student_answers(monkeypatch):
    docs=uploads.upload_documents([pdf_file(8,2,'student_A.pdf'),pdf_file(9,2,'student_B.pdf')],'pdf',SIZE)
    shared,answer_a,answer_b=[item.getvalue() for item in photo_files(3)]
    monkeypatch.setattr(uploads,'render_document',lambda doc,*_:[shared,answer_a if doc['name']=='student_A.pdf' else answer_b])
    stem=fixture_page(answer='')
    stem['records'][0]['answer_status']='not_on_page'
    responses=iter([stem,{'records':[],'answers':[{'question_no':'1','answer':'2'}]},
                         {'records':[],'answers':[{'question_no':'1','answer':'3'}]},stem])
    calls=[]
    def model(*args,**kwargs):
        calls.append(1)
        return next(responses)
    states={}
    uploads.process_pages(docs,['8'],states,model,mode='pdf',limit_bytes=SIZE,budget=2)
    uploads.process_pages(docs,['9'],states,model,mode='pdf',limit_bytes=SIZE,budget=1)
    a,b=[states[doc['file_id']]['drafts'][0] for doc in docs.values()]
    assert len(calls)==3 and b['reused_question_page'] and a['records'][0] is not b['records'][0]
    _,rows=uploads.assemble_materials(docs,list(docs),states,mode='pdf')
    assert [r['answer'] for r in rows]==['2','3']
    assert rows[0]['student_id']!=rows[1]['student_id']
    state_b=states[docs['9']['file_id']]
    del state_b['drafts'][0]
    state_b['fresh_pages']={0}
    uploads.process_pages(docs,['9'],states,model,mode='pdf',limit_bytes=SIZE,budget=1)
    assert len(calls)==4 and not state_b['drafts'][0].get('reused_question_page')
