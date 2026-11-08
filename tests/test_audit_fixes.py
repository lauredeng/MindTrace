"""Regression cases from the architecture audit; no real API or user records."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

import pytest
from core import classroom as c, collaboration as x, education as e, product as p
from test_product import workspace, quick, correction, deep, fake_call
from test_collaboration import classroom


def test_correct_final_cannot_hide_locally_wrong_process_or_skip_deep_analysis():
    w=c.new_workspace()
    batch=p.create_batch(w,'过程冲突',[dict(student_id='A',question='2*(x+3)=10',
        steps=['2*(x+3)=10','2*x+3=10','x=2'],answer='x=2')])
    sub=w['submissions'][0];calls=[]
    def model(*args,**kw):
        calls.append(kw['purpose'])
        payload=quick(sub,'correct') if kw['purpose']=='quick_grading' else deep(sub)
        payload['final_answer_status']='correct'
        return payload
    p.run_batch(w,batch['id'],model)
    record=sub['quick_checks'][-1]
    assert record['model_verdict']=='correct' and record['verdict']=='uncertain'
    assert record['final_answer_status']=='correct' and record['conflicts']
    assert calls==['quick_grading','error_analysis']


def test_reference_with_correct_answer_and_wrong_steps_is_not_published():
    _,_,sub=workspace();payload=correction()
    payload['steps']=[{'text':'2*x+3=10','reason':'错误展开'},{'text':'x=2','reason':'无效跳步'}]
    with pytest.raises(ValueError,match='参考解未发布'):
        p.validate_correction(payload,sub)
    solution=p.solve_question(sub,'full',lambda *a,**k:dict(known_conditions=[],goal='求解',method='离线',correction=payload))
    assert solution['status']=='failed' and p.correction_for(sub) is None


def test_legacy_short_result_is_guarded_without_erasing_original_model_record():
    w,b,sub=workspace();p.quick_check(sub,lambda *a,**k:quick(sub))
    old=sub['quick_checks'][-1];old.update(verdict='correct',model_verdict='correct',conflicts=[])
    assert p.latest(sub,'quick_checks')['verdict']=='uncertain'
    assert p.batch_execution(w,b['id'])['deep_required']==1
    assert old['verdict']=='correct'  # historical evidence is immutable


def test_batch_lease_covers_final_save_and_stale_retry_refreshes_before_spending():
    w,b,sub=workspace();stale=deepcopy(w);saving=Event();release=Event();calls=[]
    def persist():
        saving.set();assert release.wait(timeout=5)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first=pool.submit(p.run_batch,w,b['id'],fake_call(sub,calls),_persist=persist)
        assert saving.wait(timeout=5)
        try:
            with pytest.raises(RuntimeError,match='另一窗口'):
                p.run_batch(stale,b['id'],lambda *a,**k:pytest.fail('duplicate request'))
        finally:release.set()
        assert first.result()['status']=='processed'
    p.run_batch(stale,b['id'],lambda *a,**k:pytest.fail('stale completed batch repeated'),_prepare=lambda:w)
    assert calls==['quick_grading','error_analysis']


def test_independent_batches_are_not_blocked_by_one_batch_lease():
    from core.execution import batch_lease
    w,b,sub=workspace()
    with batch_lease(w['id'],'another-batch'):
        assert p.run_batch(w,b['id'],fake_call(sub,[]))['status']=='processed'


def test_save_adopts_merged_feedback_into_callers_snapshot_and_keeps_record_identity(classroom):
    root,teacher,student,_=classroom
    base=x.load(teacher,root);ours=deepcopy(base);sub=ours['submissions'][0]
    student_base=x.load(student,root);student_after=deepcopy(student_base)
    p.study_turn(student_after,student_after['submissions'][0],'reply','为什么？',
        lambda *a,**k:dict(message='本题解释',purpose='核对步骤',next_suggestion=''))
    x.save(student,student_base,student_after,root)
    ours['batches'][0]['name']='教师新名称'
    version=x.save(teacher,base,ours,root)
    assert ours['study_sessions'] and ours['storage_version']==version==x.version(teacher,root)
    assert ours['submissions'][0] is sub
    assert ours==x.load(teacher,root)


def test_student_adoption_remains_scoped_when_teacher_adds_another_student(classroom):
    root,teacher,student,_=classroom
    base=x.load(student,root);ours=deepcopy(base)
    tbase=x.load(teacher,root);tw=deepcopy(tbase)
    tw['submissions'].append(e.normalize_submission(dict(student_id='C',question='x=1',answer='x=1')))
    x.save(teacher,tbase,tw,root)
    p.edit_entry(ours,ours['notebook'][0]['id'],'计算失误',[],'本人说明')
    x.save(student,base,ours,root)
    assert {s['student_id'] for s in ours['submissions']}=={'A'}
    assert not ours['usage'] and not ours['events']
    assert ours==x.load(student,root)


def test_global_error_groups_use_the_same_latest_submission_scope_as_headcounts():
    w,b,sub=workspace();p.run_batch(w,b['id'],fake_call(sub,[]))
    next_batch=p.create_batch(w,'再次提交',[dict(student_id=sub['student_id'],question=sub['question'],steps=sub['steps'],answer=sub['answer'])])
    latest=w['submissions'][-1];p.run_batch(w,next_batch['id'],fake_call(latest,[]))
    assert p.per_question(w)[0]['total']==1
    assert {sid for group in p.error_groups(w) for sid in group['submission_ids']}=={latest['id']}
    assert {sid for group in p.error_groups(w,b['id']) for sid in group['submission_ids']}=={sub['id']}


@pytest.mark.parametrize('change',[
    lambda w:w['submissions'].append({'id':'missing-business-fields'}),
    lambda w:w['submissions'][0].update(steps=['x']*31),
    lambda w:w['study_sessions'].append(dict(id='session',submission_id=w['submissions'][0]['id'],student_id='OTHER',turns=[])),
    lambda w:w['batches'][0].update(submission_ids=['not-in-this-workspace']),
    lambda w:w['study_sessions'].append(dict(id='session',submission_id=[],student_id='A',turns=[])),
])
def test_invalid_nested_records_are_rejected_before_save_without_mutating_original(change):
    w,_,_=workspace();bad=deepcopy(w);change(bad)
    with pytest.raises(ValueError):c.validate_workspace(bad)
    assert c.validate_workspace(w)['submissions']==w['submissions']


def test_history_capacity_is_separate_and_never_silently_truncates():
    w=c.new_workspace();w['events']=[dict(id=str(i),command_id=str(i)) for i in range(2000)]
    assert c.commit(w,'more-history',lambda draft:None)
    assert len(w['events'])==2001
    w['events']=[dict(id=str(i),command_id=str(i)) for i in range(c.CAPACITIES['events'])]
    assert any(item['name']=='操作历史' for item in c.capacity_status(w))
    with pytest.raises(ValueError,match='下载备份'):
        c.commit(w,'over-capacity',lambda draft:None)
    assert len(w['events'])==c.CAPACITIES['events']


def test_provider_image_strips_metadata_preserves_orientation_and_original_hash():
    import base64,hashlib,io,json
    from PIL import Image
    image=Image.new('RGB',(60,30),'white');exif=Image.Exif()
    exif[274]=6;exif[315]='private-author-marker';exif[270]='private-description-marker'
    out=io.BytesIO();image.save(out,format='JPEG',exif=exif);original=out.getvalue();captured=[]
    def transport(system,blocks,**kwargs):
        encoded=blocks[1]['image_url']['url'].split(',',1)[1]
        sent=Image.open(io.BytesIO(base64.b64decode(encoded)))
        assert sent.size==(30,60) and not sent.getexif()
        captured.append(encoded)
        return dict(transcription='匿名数学材料',warnings=[],records=[])
    result=e.extract_image(original,transport)
    assert captured and result['image_ref']==hashlib.sha256(original).hexdigest()
    assert Image.open(io.BytesIO(original)).getexif()[315]=='private-author-marker'


def test_classroom_creation_limits_block_before_creating_more_files(tmp_path):
    from core.limits import UsageLimitError
    x.create('一',tmp_path,creator_id='visitor')
    x.create('二',tmp_path,creator_id='visitor')
    with pytest.raises(UsageLimitError):x.create('三',tmp_path,creator_id='visitor')
    assert len(list(tmp_path.iterdir()))==2


def test_classroom_directory_cap_cannot_be_bypassed_by_new_session(tmp_path,monkeypatch):
    from core.limits import UsageLimitError
    monkeypatch.setenv('MINDTRACE_CLASSROOM_MAX','1')
    code=x.create('已有课堂',tmp_path,creator_id='one')
    with pytest.raises(UsageLimitError):x.create('另一访客',tmp_path,creator_id='two')
    assert x.load(code,tmp_path)['submissions']==[] and len(list(tmp_path.iterdir()))==1


def test_math_runtime_fault_is_distinct_from_unsupported_and_never_echoes_input(monkeypatch):
    from core import math_tools
    _,_,sub=workspace()
    def fail(*args):raise RuntimeError('private-error-marker')
    monkeypatch.setattr(math_tools,'_equation',fail)
    result=math_tools.evidence(sub)
    assert result['status']=='failed' and result['diagnostics']
    assert 'private-error-marker' not in str(result)
