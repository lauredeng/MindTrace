"""Scoped cross-browser storage tests. No model requests or real student records."""
from copy import deepcopy
import json
import pytest
from core import collaboration as x,product as p,classroom as c,education as e
from test_product import quick,deep
from test_education import CASES

@pytest.fixture
def classroom(tmp_path):
    teacher=x.create('隔离课堂',tmp_path);before=x.load(teacher,tmp_path);w=deepcopy(before)
    b=p.create_batch(w,'教师原题',[dict(CASES[10],student_id=s) for s in ('A','B')])
    for sub in w['submissions']:
        p.quick_check(sub,lambda *a,_s=sub,**kw:quick(_s))
        p.deep_analyze(sub,lambda *a,_s=sub,**kw:deep(_s));p.sync_notebook(w,sub['id'])
    x.save(teacher,before,w,tmp_path)
    return tmp_path,teacher,x.invite(teacher,'A',tmp_path),x.invite(teacher,'B',tmp_path)

def test_codes_bind_role_and_student_and_metadata_has_hashes_only(classroom):
    root,t,a,b=classroom
    assert x.resolve(t,root)['role']=='teacher'
    assert x.resolve(a,root)['student_id']=='A'
    assert x.resolve(b,root)['student_id']=='B'
    text=next(root.glob('*/access.json')).read_text(encoding='utf-8')
    assert all(code.split('.')[1] not in text for code in (t,a,b))
    for code in ('','../invalid.token','0'*32+'.'+'x'*43,a+'x'):
        with pytest.raises(ValueError):x.resolve(code,root)

def test_student_projection_excludes_other_students_scores_and_shared_images(classroom):
    root,t,a,b=classroom;before=x.load(t,root);w=deepcopy(before)
    for s in w['submissions']:s.update(image_ref='a'*64,transcription='整页含其他学生')
    w['batches'][0]['verified_scores']={'values':{'A':1,'B':2}}
    x.save(t,before,w,root);view=x.load(a,root)
    assert {s['student_id'] for s in view['submissions']}=={'A'}
    assert {n['student_id'] for n in view['notebook']}=={'A'}
    assert all(s['image_ref'] is None and not s['transcription'] for s in view['submissions'])
    assert all(n['image_ref'] is None for n in view['notebook'])
    assert 'verified_scores' not in view['batches'][0]
    assert len(view['batches'][0]['submission_ids'])==1
    assert not view['events'] and not view['usage']

def test_student_cause_and_dialogue_arrive_in_teacher_workspace(classroom):
    root,t,a,b=classroom;base=x.load(a,root);view=deepcopy(base);entry=view['notebook'][0]
    p.edit_entry(view,entry['id'],'计算失误',[],'我漏乘了常数项')
    p.study_turn(view,view['submissions'][0],'reply','为何乘2？',lambda *a,**k:{'message':'离线解释','purpose':'验证题目关联','next_suggestion':''})
    x.save(a,base,view,root)
    teacher=x.load(t,root)
    assert next(n for n in teacher['notebook'] if n['student_id']=='A')['notes']=='我漏乘了常数项'
    assert teacher['study_sessions'][0]['submission_id']==entry['submission_id']
    assert not x.load(b,root)['study_sessions']

@pytest.mark.parametrize('change',['teacher_review','foreign_student','original_answer'])
def test_student_cannot_modify_teacher_or_other_student_records(classroom,change):
    root,t,a,b=classroom;base=x.load(a,root);w=deepcopy(base)
    if change=='teacher_review':w['reviews'].append({'id':'forged'})
    elif change=='foreign_student':w['notebook'][0]['student_id']='B'
    else:w['submissions'][0]['answer']='伪造原答'
    with pytest.raises(ValueError):x.save(a,base,w,root)

def test_stale_independent_writes_merge_without_losing_either_actor(classroom):
    root,t,a,b=classroom;tbase=x.load(t,root);sbase=x.load(a,root)
    teacher=deepcopy(tbase);student=deepcopy(sbase)
    sub=teacher['submissions'][0];c.review(teacher,sub['id'],'confirm','教师确认',[],'核对原文','review-A',first_error_step=2)
    p.edit_entry(student,student['notebook'][0]['id'],'审题失误',[],'学生自己的解释')
    x.save(t,tbase,teacher,root);x.save(a,sbase,student,root)
    current=x.load(t,root)
    assert current['reviews'][-1]['label']=='教师确认'
    assert next(n for n in current['notebook'] if n['student_id']=='A')['notes']=='学生自己的解释'
    assert len(current['submissions'])==2

def test_conflicting_same_field_is_rejected_and_disk_remains_intact(classroom):
    root,t,a,b=classroom;base=x.load(a,root);one=deepcopy(base);two=deepcopy(base)
    p.edit_entry(one,one['notebook'][0]['id'],'计算失误',[],'第一次修改')
    p.edit_entry(two,two['notebook'][0]['id'],'审题失误',[],'冲突修改')
    x.save(a,base,one,root)
    with pytest.raises(ValueError,match='并发修改'):x.save(a,base,two,root)
    assert x.load(a,root)['notebook'][0]['notes']=='第一次修改'

def test_code_revocation_classroom_isolation_and_teacher_only_issuing(classroom):
    root,t,a,b=classroom
    with pytest.raises(ValueError):x.invite(a,'B',root)
    fresh=x.invite(t,'A',root)
    with pytest.raises(ValueError):x.load(a,root)
    assert x.resolve(fresh,root)['student_id']=='A'
    other=x.create('其他课堂',root)
    with pytest.raises(ValueError):x.save(other,x.load(t,root),x.load(t,root),root)
    assert not x.load(other,root)['submissions']

def test_student_new_question_is_personal_and_teacher_sources_stay_immutable(classroom):
    root,t,a,b=classroom;base=x.load(a,root);view=deepcopy(base)
    own=e.normalize_submission(dict(CASES[10],student_id='A'),source='self_study');view['submissions'].append(own)
    x.save(a,base,view,root)
    assert len(x.load(a,root)['submissions'])==2 and len(x.load(b,root)['submissions'])==1

def test_concurrent_append_to_same_submission_keeps_both_stage_lists(classroom):
    root,t,a,b=classroom;tbase=x.load(t,root);sbase=x.load(a,root)
    teacher=deepcopy(tbase);student=deepcopy(sbase)
    teacher['submissions'][0]['quick_checks'].append(dict(teacher['submissions'][0]['quick_checks'][0],id='teacher-new-check'))
    p.solve_question(student['submissions'][0],'hint',lambda *a,**k:{'known_conditions':[],'goal':'了解方法','method':'离线提示','correction':{'answer':'','steps':[],'knowledge_points':[],'category':p.UNKNOWN,'category_basis':'方向提示','supplements':[],'uncertainties':[]}})
    x.save(t,tbase,teacher,root);x.save(a,sbase,student,root)
    row=x.load(t,root)['submissions'][0]
    assert row['quick_checks'][-1]['id']=='teacher-new-check' and row['solutions']


def test_teacher_source_resync_and_student_notes_merge_including_timestamps(classroom):
    root,t,a,b=classroom;tbase=x.load(t,root);sbase=x.load(a,root)
    teacher=deepcopy(tbase);student=deepcopy(sbase);sub=teacher['submissions'][0]
    c.review(teacher,sub['id'],'confirm','新复核',[],'原文不变','new-review',first_error_step=2)
    p.sync_notebook(teacher,sub['id'])
    p.edit_entry(student,student['notebook'][0]['id'],'计算失误',[],'学生解释')
    x.save(t,tbase,teacher,root);x.save(a,sbase,student,root)
    current=x.load(t,root);entry=next(n for n in current['notebook'] if n['student_id']=='A')
    assert entry['notes']=='学生解释' and entry['source_id']==current['reviews'][-1]['id']


def test_student_cannot_rebind_notebook_to_another_student_source(classroom):
    root,t,a,b=classroom;base=x.load(a,root);w=deepcopy(base)
    foreign=x.load(b,root)['submissions'][0]['id'];w['notebook'][0]['submission_id']=foreign
    with pytest.raises(ValueError,match='自己的原始作答'):x.save(a,base,w,root)

def test_corrupt_access_metadata_is_a_clean_denial(classroom):
    root,t,a,b=classroom;meta=next(root.glob('*/access.json'));meta.write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='访问码'):x.resolve(t,root)


def test_shared_image_redaction_does_not_cause_role_switch_history_churn(classroom):
    root,t,a,b=classroom;base=x.load(t,root);w=deepcopy(base)
    for sub in w['submissions']:sub['image_ref']='c'*64;p.sync_notebook(w,sub['id'])
    x.save(t,base,w,root);before=len(x.load(t,root)['book_events'])
    for code in (a,t,a,t):
        base=x.load(code,root);w=deepcopy(base)
        for sub in w['submissions']:p.sync_notebook(w,sub['id'])
        assert len(w['book_events'])==len(base['book_events'])
    assert len(x.load(t,root)['book_events'])==before
