"""Confirmed heatmap and notebook presentation regression, no model requests."""
from copy import deepcopy
import math
import pytest
from core import education as e,product as p,presentation as v,classroom as c
from test_product import quick,deep
from test_education import CASES

def fixture():
    w=c.new_workspace()
    rows=[]
    for sid in ('ERROR','PENDING','UNREADABLE','MISSING','CORRECT'):
        row=dict(CASES[10],student_id=sid,question_type='填空题')
        if sid=='UNREADABLE':row['submission_status']='unreadable'
        if sid=='MISSING':row.update(steps=[],answer='',submission_status='not_submitted')
        if sid=='CORRECT':row.update(steps=['x+3=5','x=2'],answer='x=2')
        rows.append(row)
    batch=p.create_batch(w,'确认口径',rows)
    for submission_id in [s['id'] for s in w['submissions']]:
        sub=next(s for s in w['submissions'] if s['id']==submission_id)
        if sub['student_id']=='MISSING':continue
        q=quick(sub,'correct' if sub['student_id']=='CORRECT' else 'incorrect')
        p.quick_check(sub,lambda *a,_q=q,**kw:_q)
        if sub['student_id'] in ('ERROR','UNREADABLE'):
            p.deep_analyze(sub,lambda *a,_s=sub,**kw:deep(_s))
            c.review(w,sub['id'],'confirm','展开错误',['分配律'],'测试复核','confirm-'+sub['student_id'],first_error_step=2)
        if sub['student_id']=='CORRECT':v.confirm_short(w,sub['id'])
    return w,batch

def test_heatmap_excludes_pending_missing_unreadable_even_if_reviewed():
    w,b=fixture();r=v.heatmap_rows(w,b['id'])[0]
    assert (r['errors'],r['correct'],r['valid'])==(1,1,2)
    assert (r['pending'],r['not_submitted'],r['unreadable'])==(1,1,1)
    assert r['ratio']==.5
    assert v.batch_summary(w,b['id'])['submitted_students']==4

def test_reliable_mean_requires_complete_finite_teacher_totals():
    w,b=fixture()
    assert v.batch_summary(w,b['id'])['average'] is None
    v.save_scores(w,b['id'],{'ERROR':80},100)
    assert v.batch_summary(w,b['id'])['average'] is None
    values={'ERROR':80,'PENDING':90,'UNREADABLE':70,'CORRECT':60}
    v.save_scores(w,b['id'],values,100)
    assert v.batch_summary(w,b['id'])['average']==75
    for invalid in (float('nan'),float('inf'),-1,101,True):
        with pytest.raises(ValueError):v.save_scores(w,b['id'],{'ERROR':invalid},100)
    with pytest.raises(ValueError):v.save_scores(w,b['id'],{'FOREIGN':80},100)

def test_zero_valid_has_no_error_ratio_and_no_invented_roster():
    w=c.new_workspace()
    b=p.create_batch(w,'无可靠统计',[dict(CASES[10],student_id='A',steps=[],answer='')])
    r=v.heatmap_rows(w,b['id'])[0]
    assert r['ratio'] is None and r['valid']==0 and r['errors']==0
    assert r['not_submitted']==1
    b['roster']=['A','B','C']
    assert v.heatmap_rows(w,b['id'])[0]['not_submitted']==3

def test_question_type_and_subpart_identity_survive_save(tmp_path):
    w=c.new_workspace()
    rows=[dict(CASES[10],student_id='A',question_type='解答题',parent_question_no='17',subquestion_no=str(i),question_no='17('+str(i)+')') for i in (1,2)]
    b=p.create_batch(w,'两小问',rows)
    records=v.heatmap_rows(w,b['id'])
    assert len(records)==2 and [r['label'] for r in records]==['17(1)','17(2)']
    assert len({r['id'] for r in records})==2
    path=tmp_path/'store.json';c.save(w,path)
    assert [r['label'] for r in v.heatmap_rows(c.load(path),b['id'])]==['17(1)','17(2)']


def test_shared_pdf_stem_collapses_ocr_variants_without_combining_different_exams():
    w=c.new_workspace()
    stems=['圆的半径是几？','求这个圆的半径。','求圆的面积。']
    materials=[]
    rows=[]
    for sid,stem,original,image in zip('ABC',stems,'abc','112'):
        row=dict(student_id=sid,question=stem,answer='2',question_type='填空题',question_no='1',
                 steps=[],image_ref=image*64,source_pages=[1])
        rows.append(row)
        materials.append(dict(student_id=sid,kind='pdf',identity_status='file_group',pages=[
            dict(file_id=original*64,original_file=original*64,original_image=image*64,page_number=1,
                 filename=sid+'.pdf',transcription='',recognition_status='recognized',recognized_records=[row])]))
    b=p.create_batch(w,'题面证据',rows,materials=materials,grading_policy=p.CLASSROOM_POLICY)
    p.quick_check(w['submissions'][0],lambda *a,**k:dict(verdict='correct',process_checked=False,basis='答案核对。'))
    cells=v.heatmap_rows(w,b['id'],automatic=True)
    assert sorted((len(r['submission_ids']),r['correct'],r['waiting']) for r in cells)==[(1,0,1),(2,1,1)]

def test_old_unknown_not_guessed_and_metadata_update_does_not_rewrite_math():
    w,b=fixture();sub=w['submissions'][0];before=sub['question'];fingerprint=sub['fingerprint']
    rows=[dict(q,question_type='选择题',parent_question_no='',subquestion_no='') for q in b['questions']]
    v.update_types(w,b['id'],rows)
    assert v.heatmap_rows(w,b['id'])[0]['question_type']=='选择题'
    assert sub['question']==before and sub['fingerprint']==fingerprint
    assert v.kind({})=='未分类'
    with pytest.raises(ValueError):v.update_types(w,b['id'],[dict(rows[0],question_type='随便猜')])

def test_notebook_personal_type_keeps_original_source_and_cause_counts_follow_edit():
    w,b=fixture();sub=w['submissions'][0]
    n=p.sync_notebook(w,sub['id']);v.edit_type(w,n['id'],'解答题')
    p.edit_entry(w,n['id'],'计算失误',[],'',True)
    groups,unknown=v.cause_distribution([n])
    assert groups['计算失误']['confirmed']==1 and unknown==0
    p.edit_entry(w,n['id'],'公式或定理误用',[],'',False)
    groups,_=v.cause_distribution([n])
    assert '计算失误' not in groups and groups['公式或定理误用']['suggested']==1
    p.sync_notebook(w,sub['id'])
    assert v.kind(n)=='解答题' and sub['question_type']=='填空题'
    p.delete_entry(w,n['id'])
    assert v.cause_distribution([n])==({},0)

def test_drilldown_scope_never_includes_another_questions_students():
    w=c.new_workspace()
    b=p.create_batch(w,'来源隔离',[dict(CASES[10],student_id='A'),dict(CASES[10],question='解方程2*(x+3)=12',student_id='B')])
    for sub in w['submissions']:
        p.quick_check(sub,lambda *a,_s=sub,**kw:quick(_s))
        data=deep(sub)
        if sub['student_id']=='B':
            data['correction']['answer']='x=3'
            data['correction']['steps']=[{'text':'x+3=6','reason':'等式两边同除2'},{'text':'x=3','reason':'减3'}]
        p.deep_analyze(sub,lambda *a,_d=data,**kw:_d)
    first=w['submissions'][0]
    groups=v.question_error_groups(w,b['id'],[first['id']])
    assert groups and all(g['students']==['A'] for g in groups)
    assert all(g['submission_ids']==[first['id']] for g in groups)

def test_short_confirmation_requires_actual_review_action_and_invalidates_on_regrade():
    w=c.new_workspace();b=p.create_batch(w,'短批改',[dict(CASES[10],steps=['x+3=5','x=2'],answer='x=2')]);sub=w['submissions'][0]
    payload=quick(sub,'correct');p.quick_check(sub,lambda *a,**kw:payload)
    assert v.heatmap_rows(w,b['id'])[0]['pending']==1
    v.confirm_short(w,sub['id'])
    assert v.heatmap_rows(w,b['id'])[0]['correct']==1
    sub=w['submissions'][0]
    p.quick_check(sub,lambda *a,**kw:payload,True)
    assert v.heatmap_rows(w,b['id'])[0]['pending']==1


def test_uploaded_blank_paper_counts_student_without_valid_item():
    w=c.new_workspace();b=p.create_batch(w,'已交空白卷',[dict(CASES[10],student_id='BLANK',steps=[],answer='')])
    assert v.batch_summary(w,b['id'])['submitted_students']==1
    assert v.heatmap_rows(w,b['id'])[0]['valid']==0


def test_pie_uses_classified_count_denominator_and_reclassification():
    rows=[{'id':str(i),'primary_category':cat,'category_confirmed':i%2==0,'active_error':True,'deleted':False}
          for i,cat in enumerate(['计算失误','计算失误','计算失误','审题失误',p.UNKNOWN])]
    slices,total,unknown=v.cause_slices(rows)
    assert total==4 and unknown==1
    byname={r['label']:r for r in slices}
    assert byname['计算失误']['count']==3 and byname['计算失误']['percent']==75
    assert byname['审题失误']['count']==1 and byname['审题失误']['percent']==25
    assert sum(r['percent'] for r in slices)==100
    original_color=byname['审题失误']['color']
    rows[0]['primary_category']='审题失误'
    slices,total,_=v.cause_slices(rows)
    assert total==4 and all(r['count']==2 and r['percent']==50 for r in slices)
    assert next(r['color'] for r in slices if r['label']=='审题失误')==original_color


def test_pie_excludes_deleted_corrected_and_supports_single_slice():
    base={'primary_category':'计算失误','category_confirmed':True,'active_error':True,'deleted':False}
    rows=[dict(base,id='1'),dict(base,id='2',deleted=True),dict(base,id='3',active_error=False)]
    slices,total,unknown=v.cause_slices(rows)
    assert total==1 and unknown==0 and slices[0]['percent']==100
    assert v.cause_slices([])==([],0,0)

def test_pie_display_rounding_matches_between_chart_and_legend():
    rows=[{'id':str(i),'primary_category':'审题失误' if i==0 else '计算失误','category_confirmed':True,'active_error':True,'deleted':False} for i in range(16)]
    slices,total,_=v.cause_slices(rows)
    tiny=next(r for r in slices if r['label']=='审题失误')
    assert total==16 and tiny['percent']==6.25 and tiny['percent_label']=='6.3'


def test_correctness_uses_only_confirmed_valid_records_and_empty_is_unknown():
    w,b=fixture()
    summary=v.batch_summary(w,b['id'])
    assert summary['correctness']==.5
    assert summary['correct_count']==1 and summary['valid_count']==2
    empty=c.new_workspace()
    b2=p.create_batch(empty,'尚未批改',[dict(CASES[10],student_id='A')])
    assert v.batch_summary(empty,b2['id'])['correctness'] is None
