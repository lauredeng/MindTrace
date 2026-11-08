"""Bounded intake for teacher image and PDF batches."""
from pathlib import Path
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import io
import re
import shutil
import subprocess
import tempfile

from PIL import Image, ImageOps
from core.ocr import prepare_image

MAX_CLASS_FILES = 100
MAX_CLASS_PAGES = 160
MAX_CLASS_BYTES = 128 * 1024 * 1024
MAX_PDF_BYTES = 24 * 1024 * 1024
MAX_PDF_PAGES = 24
MAX_TEACHER_FILES = 100
MAX_PHOTOS = 24
MAX_TEACHER_BYTES = 512 * 1024 * 1024
IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.webp'}


def _pdf_pages(data, remaining, *, max_bytes=MAX_PDF_BYTES):
    if not data.startswith(b'%PDF-') or len(data)>max_bytes:
        raise ValueError('PDF 格式无效或超过单文件大小限制。')
    info,render=shutil.which('pdfinfo'),shutil.which('pdftoppm')
    if not info or not render:
        raise ValueError('服务器缺少 PDF 转图工具 Poppler，请先上传 JPG 或 PNG。')
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with tempfile.TemporaryDirectory(prefix='mindtrace-pdf-') as folder:
        source=Path(folder)/'upload.pdf'
        source.write_bytes(data)
        try:
            meta=subprocess.run([info,str(source)],capture_output=True,check=True,timeout=12,creationflags=flags)
            match=re.search(rb'^Pages:\s*(\d+)\s*$',meta.stdout,re.MULTILINE)
            pages=int(match[1]) if match else 0
            if not 1<=pages<=min(MAX_PDF_PAGES,remaining):
                raise ValueError(f'PDF 页数超出可用范围（最多 {min(MAX_PDF_PAGES,remaining)} 页）。')
            target=Path(folder)/'page'
            subprocess.run([render,'-f','1','-l',str(pages),'-scale-to','2000','-jpeg',
                            '-jpegopt','quality=90',str(source),str(target)],
                           capture_output=True,check=True,timeout=45,creationflags=flags)
        except (OSError,subprocess.SubprocessError):
            raise ValueError('无法读取该 PDF，请检查文件是否损坏、加密或包含无法渲染的页面。') from None
        files=sorted(Path(folder).glob('page-*.jpg'))
        if len(files)!=pages:
            raise ValueError('PDF 有页面无法转成图片。')
        return [path.read_bytes() for path in files]


def expand_files(files, *, allow_pdf):
    maximum=MAX_CLASS_FILES if allow_pdf else 5
    if len(files)>maximum or sum(file.size for file in files)>MAX_CLASS_BYTES:
        raise ValueError(f'一次最多 {maximum} 份文件，总大小不超过 128 MB。')
    pages=[]
    errors=[]
    used_bytes=0
    for file in files:
        try:
            data=file.getvalue()
            if allow_pdf and Path(file.name).suffix.lower()=='.pdf':
                extracted=_pdf_pages(data,MAX_CLASS_PAGES-len(pages))
                current=[(f'{file.name} · 第 {i} 页',page) for i,page in enumerate(extracted,1)]
            else:
                current=[(file.name,data)]
            if len(pages)+len(current)>MAX_CLASS_PAGES:
                raise ValueError('整批最多 160 页，请拆成两批。')
            total=used_bytes+sum(len(data) for _,data in current)
            if total>MAX_CLASS_BYTES:
                raise ValueError('转图后的页面总量超过 128 MB，请拆成两批。')
            for _,page in current:
                prepare_image(page)
            pages.extend(current)
            used_bytes=total
        except ValueError as exc:
            errors.append((file.name,str(exc)))
    return pages,errors


def student_number(value):
    """Canonical comparison keeps leading zeroes and avoids guessing a person's name."""
    value=value.strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{0,79}',value):
        raise ValueError('学生编号请使用字母、数字、连字符或下划线。')
    return value


def upload_documents(files, mode, limit_bytes):
    """Keep source files separate; a rendering error only blocks its own file."""
    maximum=MAX_TEACHER_FILES if mode=='pdf' else MAX_PHOTOS
    if len(files)>maximum or sum(f.size for f in files)>MAX_TEACHER_BYTES:
        raise ValueError(f'此入口一次最多 {maximum} 份文件，合计最多 512 MB。')
    documents={}
    for f in files:
        data=f.getvalue()
        file_id=sha256(data).hexdigest()
        suffix=Path(f.name).suffix.lower()
        error=''
        try:
            if not data or len(data)>limit_bytes:
                raise ValueError(f'单文件最多 {limit_bytes//(1024*1024)} MB。')
            if mode=='pdf':
                if suffix!='.pdf' or not data.startswith(b'%PDF-'):
                    raise ValueError('请上传有效的 PDF 文件。')
            elif suffix in IMAGE_TYPES:
                prepare_image(data,max_bytes=limit_bytes)
            else:
                raise ValueError('请上传 PNG、JPEG 或 WEBP 图片。')
        except ValueError as exc:
            error=str(exc)
        documents[f.file_id]={'file_id':file_id,'name':f.name[:200],'data':data,'error':error}
    return documents


def duplicate_files(documents):
    files=Counter(d['file_id'] for d in documents.values())
    return {key for key,d in documents.items() if files[d['file_id']]>1}


def render_document(document, mode, limit_bytes):
    data=document['data']
    return _pdf_pages(data,MAX_PDF_PAGES,max_bytes=limit_bytes) if mode=='pdf' else [data]


def reject_existing(workspace,name,materials):
    previous=[m for batch in workspace['batches'] if batch['name'].strip().casefold()==name.strip().casefold()
              for m in batch.get('materials',[])]
    students={m['student_id'].casefold() for m in previous}
    files={p['file_id'] for m in previous for p in m['pages']}
    if any(page['file_id'] in files for m in materials for page in m['pages']):
        raise ValueError('同名作业已保存过这些原始文件，请到已有批次查看。')
    if any(m['student_id'].casefold() in students for m in materials):
        raise ValueError('同名作业已包含此学生，请检查原批次；已有作答不会被覆盖。')


def page_region(data,bounds):
    with Image.open(io.BytesIO(data)) as source:
        image=ImageOps.exif_transpose(source)
        width,height=image.size
        if height<4:raise ValueError('图片过小，无法分区识别。')
        start,end=bounds
        top,bottom=height*start//100,(height*end+99)//100
        region=image.crop((0,top,width,bottom)).convert('RGB')
        output=io.BytesIO()
        region.save(output,format='JPEG',quality=94)
        return output.getvalue()


def combine_regions(data,regions):
    rows=[]
    for part in regions:
        for row in part['records']:
            if row not in rows:rows.append(row)
    if len(rows)>30:
        raise ValueError('分区结果题目过多，请将原页分开上传后校对。')
    answers=[]
    for part in regions:
        for answer in part['answers']:
            if answer not in answers:answers.append(answer)
    if len(answers)>40:raise ValueError('分区结果作答过多，请缩小页面区域。')
    return dict(regions[0],image_ref=sha256(data).hexdigest(),records=rows,answers=answers,split_page=True,
                warnings=['本页由上下两个重叠区域识别，请对照原页核对分界处。']+
                         [w for part in regions for w in part['warnings']],
                no_work=all(part['no_work'] for part in regions))


def process_pages(documents,keys,states,call,*,mode,limit_bytes,budget=20,progress=lambda *_:None):
    from core import education as e, product as p
    from core.ai import InvalidModelJSON, OutputTruncatedError
    from core.limits import UsageLimitError
    previous=[]
    previous_page=[]
    reusable={draft['question_cache_key']:draft for state in states.values() for draft in state['drafts'].values()
              if 'question_cache_key' in draft}
    for key in keys:
        doc=documents[key]
        state=states.setdefault(doc['file_id'],{'pages':[],'drafts':{},'error':''})
        if doc['error']:
            continue
        if not state['pages']:
            try:state['pages']=render_document(doc,mode,limit_bytes)
            except ValueError as exc:
                state['error']=str(exc)
                continue
            except OSError:
                state['error']='临时页面读取失败，请单独重试此文件。'
                continue
        if mode=='pdf':
            previous=[]
            previous_page=[]
        fresh=state.get('fresh_pages',set())
        for index,data in enumerate(state['pages']):
            draft=state['drafts'].get(index)
            parent=open_parent(previous_page)
            cache_key=p.digest([sha256(data).hexdigest(),previous,parent]) if mode=='pdf' and draft is None else None
            if cache_key in reusable and index not in fresh:
                draft=deepcopy(reusable[cache_key])
                draft['reused_question_page']=True
                state['drafts'][index]=draft
                state.get('splits',{}).pop(index,None)
                state['error']=''
                progress(doc['name'],index+1,len(state['pages']),'复用相同题面')
            format_retry=set()
            while draft is None:
                if not budget:return '已达到本轮识别请求数，请继续下一批。'
                budget-=1
                splits=state.setdefault('splits',{})
                parts=splits.get(index)
                completed=parts['done'] if parts else []
                bounds=parts['bounds'][len(completed)] if parts else None
                current=previous+[row for part in completed for row in part['records']]
                catalog={p.item_key(row):row['question'] for row in current}
                known=[{'id':qid,'question':question} for qid,question in list(catalog.items())[-10:]]
                region={(0,56):'上半部分',(44,100):'下半部分'}.get(bounds,f'{bounds[0]}%–{bounds[1]}% 区域') if bounds else None
                progress(doc['name'],index+1,len(state['pages']),region)
                try:
                    source=data if bounds is None else page_region(data,bounds)
                    result=e.extract_image(source,call,known_questions=known,compact=True,
                                           assignment_page=True,region=region,open_question=parent,
                                           repair_format=bounds in format_retry,max_bytes=limit_bytes)
                    if not (result['records'] or result['answers'] or result['no_work']):
                        raise ValueError('本页未识别出题干或作答，请检查原图后重试。')
                    if parts is None:
                        draft=result
                    elif len(completed)+1<len(parts['bounds']):
                        completed.append(result)
                    else:
                        draft=combine_regions(data,[*completed,result])
                except InvalidModelJSON:
                    if bounds not in format_retry:
                        format_retry.add(bounds)
                        continue
                    state['error']=f'第 {index+1} 页{region or ""}的识别回复格式异常。已保留成功的部分，请点击「重试当前文件」继续。'
                    break
                except OutputTruncatedError:
                    if parts is None:
                        splits[index]={'done':[],'bounds':[(0,56),(44,100)]}
                        continue
                    start,end=bounds
                    if end-start>=50:
                        middle=(start+end)//2
                        parts['bounds'][len(completed):len(completed)+1]=[(start,middle+3),(middle-3,end)]
                        continue
                    state['error']=f'第 {index+1} 页{region}内容过密，分区识别仍未完成。请将这页分成更小的区域后重试。'
                    break
                except UsageLimitError as exc:
                    state['error']=f'第 {index+1} 页{region or ""}：{exc}'
                    return str(exc)
                except (RuntimeError,ValueError,OSError) as exc:
                    state['error']=f'第 {index+1} 页{region or ""}：'+('无法读取页面图像。' if isinstance(exc,OSError) else str(exc))
                    break
                if draft:
                    if (cache_key and draft['records'] and not draft['answers'] and
                        all(row.get('answer_status')=='not_on_page' and not row['steps'] and not row['answer']
                            for row in draft['records'])):
                        draft['question_cache_key']=cache_key
                        reusable[cache_key]=draft
                    state['drafts'][index]=draft
                    splits.pop(index,None)
                    fresh.discard(index)
                    state['error']=''
            if draft is None:
                if mode=='photos':return ''
                break
            previous.extend(draft['records'])
            previous_page=draft['records']
    return ''


def question_number(item):
    import unicodedata
    value=unicodedata.normalize('NFKC',item['question_no']).strip().rstrip('.、:')
    match=re.fullmatch(r'(?:第\s*)?(\d+)\s*题?\s*(?:(?:[.\-]\s*)?\(?\s*(\d+)\s*\)?)?',value)
    if item['parent_question_no'] and item['subquestion_no']:
        parent=re.search(r'\d+',item['parent_question_no'])
        child=re.search(r'\d+',item['subquestion_no'])
        if parent and child:return int(parent[0]),int(child[0])
    if match:return int(match[1]),int(match[2]) if match[2] else None
    return None


def open_parent(records):
    if not records:return None
    last=records[-1]
    label=question_number(last)
    shared=last.get('stem_status')=='shared' or (last.get('stem_status')=='continued' and last.get('question_type')=='解答题')
    if label and label[1] is None and shared:
        return label[0]
    return None


def orphan_subquestion(item):
    import unicodedata
    text=unicodedata.normalize('NFKC',item['subquestion_no'] or item['question_no']).strip()
    if item['subquestion_no'] and not item['parent_question_no']:
        match=re.fullmatch(r'\(?(\d+)\)?',text)
    else:
        match=re.fullmatch(r'\((\d+)\)',text)
    return int(match[1]) if match else None


def merge_work(row,item,number):
    if number not in row['source_pages']:row['source_pages'].append(number)
    overlap=next((n for n in range(min(len(row['steps']),len(item['steps'])),0,-1)
                  if row['steps'][-n:]==item['steps'][:n]),0)
    row['steps'].extend(item['steps'][overlap:])
    if item['answer']:
        if row['answer'] and row['answer']!=item['answer']:
            row['answer']=('[无法辨认] '+row['answer']+' / '+item['answer'])[:2000]
        else:row['answer']=item['answer']
    if item.get('answer_status')=='unreadable':row['unreadable_work']=True


def assemble_materials(documents,order,states,*,mode):
    from core import product as p
    groups=[[key] for key in order] if mode=='pdf' else [order]
    if not order or duplicate_files(documents):
        raise ValueError('请移除重复文件。')
    materials,rows=[],[]
    for keys in groups:
        ids=sorted(documents[key]['file_id'] for key in keys)
        student='PAPER-'+(ids[0] if mode=='pdf' else sha256(''.join(ids).encode()).hexdigest())
        pages,questions=[],{}
        numbered={}
        work={}
        answers=[]
        previous_records=[]
        for key in keys:
            doc=documents[key]
            state=states.get(doc['file_id'],{})
            if doc['error'] or not state.get('pages') or len(state['pages'])!=len(state['drafts']):
                raise ValueError('请先完成所有保留文件的识别。')
            for index in range(len(state['pages'])):
                draft=state['drafts'][index]
                number=len(pages)+1
                page={'file_id':doc['file_id'],'original_file':doc['file_id'],'filename':doc['name'],
                      'page_number':number,'original_image':draft['image_ref'],'transcription':draft['transcription'],
                      'recognized_records':draft['records'],'recognized_answers':draft['answers'],
                      'recognition_status':'no_work' if draft['no_work'] else 'recognized'}
                pages.append(page)
                answers.extend((number,answer) for answer in draft['answers'])
                parent=open_parent(previous_records)
                previous_records=draft['records']
                for item in draft['records']:
                    label=question_number(item)
                    orphan=orphan_subquestion(item)
                    if parent is not None and orphan is not None and (not label or label[1] is None):
                        label=(parent,orphan)
                        item=dict(item,question_no=f'{parent}({orphan})',parent_question_no=str(parent),subquestion_no=str(orphan))
                    question=(label,p.item_key(item))
                    candidates=numbered.get(label,[]) if label else []
                    stem=item.get('stem_status','complete')
                    if len(candidates)==1 and (stem!='complete' or questions[candidates[0]]['stem_status']!='complete'):
                        question=candidates[0]
                    if question not in questions:
                        questions[question]=dict(item,student_id=student,source_pages=[],steps=[],answer='')
                        if label:numbered.setdefault(label,[]).append(question)
                    else:
                        row=questions[question]
                        if stem=='complete' and row['stem_status']!='complete':
                            row.update(question=item['question'],stem_status='complete')
                        elif stem=='fragment' and row['stem_status']=='continued' and item['question']!=row['question']:
                            row.update(question=row['question']+'\n'+item['question'],stem_status='complete')
                    work.setdefault(question,[]).append((number,item))
        if not questions:raise ValueError('有一份作业未提取到题目，请校对原文件或移除后再提交。')
        unmatched=[]
        for number,item in answers:
            candidates=numbered.get(question_number(item),[])
            if len(candidates)==1:
                work[candidates[0]].append((number,item))
            elif item['steps'] or item['answer'] or item['answer_status'] in ('unreadable','continued'):
                unmatched.append(f'第 {number} 页 · {item["question_no"] or "题号不清"}')
        if unmatched:
            raise ValueError(pages[0]['filename']+' 有作答未找到唯一对应题目：'+'、'.join(dict.fromkeys(unmatched))+'。请核对题号和缺页。')
        parents={label[0] for label in numbered if label[1] is not None}
        for (label,key),row in questions.items():
            if (label and label[1] is None and label[0] in parents and row['stem_status'] in ('continued','shared')
                and not any(item['steps'] or item['answer'] for _,item in work[(label,key)])):
                continue
            for number,item in sorted(work[(label,key)],key=lambda entry:entry[0]):
                merge_work(row,item,number)
            if label and label[1] is not None:
                row.update(parent_question_no=str(label[0]),subquestion_no=str(label[1]))
                common=numbered.get((label[0],None),[])
                if len(common)==1 and questions[common[0]].get('stem_status') in ('continued','shared'):
                    shared=questions[common[0]]['question']
                    if p.question_key(shared)!=p.question_key(row['question']) and re.sub(r'\s+','',shared) not in re.sub(r'\s+','',row['question']):
                        row['question']=shared+'\n'+row['question']
                    row['source_pages']=list(set(row['source_pages'])|{number for number,_ in work[common[0]]})
            unreadable=row.pop('unreadable_work',False)
            if row.pop('stem_status')!='complete' or (unreadable and not (row['answer'] or row['steps'])):
                row['answer']=('[无法辨认] '+row['answer']).strip()[:2000]
            row['source_pages'].sort()
            row['image_ref']=pages[row['source_pages'][0]-1]['original_image']
            row['steps']='\n'.join(row['steps'])
            row['transcription']='\n'.join(pages[n-1]['transcription'] for n in row['source_pages'])[:20000]
            rows.append(row)
        materials.append({'student_id':student,'kind':mode,'identity_status':'file_group','pages':pages})
    return materials,rows
