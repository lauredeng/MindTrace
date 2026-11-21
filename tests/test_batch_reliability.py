"""Fault-injection checks; synthetic replies, no paid model requests."""
from copy import deepcopy

import pytest

from core import classroom as c, presentation as v, product as p
from core.ai import ServiceUnavailable
from core.limits import UsageLimitError, auto_resume
from test_education import report
from test_product import fake_call, workspace


def test_completed_uncertain_is_review_work_not_repeated_model_work():
    w=c.new_workspace()
    batch=p.create_batch(w,'证明题复核',[
        dict(student_id='1001',question='求证：对任意正数 a、b，有 a+b≥2√(ab)。',
             question_type='解答题',steps=['设 a>0，b>0。'],answer='a+b≥2√(ab)')
    ],grading_policy=p.CLASSROOM_POLICY)
    sub=w['submissions'][0]
    calls=[]
    def model(*args,**kwargs):
        calls.append(kwargs['purpose'])
        if kwargs['purpose']=='quick_grading':
            return dict(verdict='uncertain',process_checked=True,basis='缺少完整证明，交由教师复核。',
                        evidence_id='S1',first_error_step=None)
        return report(sub,overall='insufficient_evidence')
    result=p.run_batch(w,batch['id'],model)
    assert result['complete']==1 and result['needs_review']==1
    assert result['retryable_remaining']==0 and result['status']=='processed'
    assert v.record_state(w,sub,automatic=True)=='pending'
    assert v.batch_summary(w,batch['id'])['status']=='已处理 · 待教师复核'
    # Render the actual teacher page: no whole-batch retry CTA for human review.
    from streamlit.testing.v1 import AppTest
    def teacher_page(workspace,batch_id):
        import streamlit as st
        from ui.product import teacher
        class Runtime:
            root=None
            assigned_student=None
            access=None
            shared=True
            def __init__(self):self.w=workspace
            def ready(self):return False
            def image(self,ref):return None
        st.session_state['v12_batch']=batch_id
        teacher(Runtime())
    page=AppTest.from_function(teacher_page,args=(w,batch['id'])).run()
    assert not page.exception
    assert any('已完成 AI 核验' in entry.value for entry in page.info)
    assert not any('未完成的批改' in button.label for button in page.button)
    assert calls==['quick_grading','error_analysis']
    old=deepcopy(sub['analyses'])
    p.run_batch(w,batch['id'],lambda *a,**k:pytest.fail('Repeated paid review'))
    assert sub['analyses']==old
    # Explicit single-question regeneration remains available.
    p.deep_analyze(sub,model,force=True,teacher_only=True)
    assert len(sub['analyses'])==2


def test_each_result_saved_before_interrupted_ui_then_reload_resumes(tmp_path):
    w,batch,sub=workspace()
    path=tmp_path/'checkpoint.json'
    calls=[]
    class PageInterrupted(BaseException):
        pass
    def interrupted(*args):
        raise PageInterrupted()
    with pytest.raises(PageInterrupted):
        p.run_batch(w,batch['id'],fake_call(sub,calls),interrupted,
                    _persist=lambda:c.save(w,path))
    loaded=c.load(path)
    restored=loaded['submissions'][0]
    assert len(restored['quick_checks'])==1 and not restored['analyses']
    assert loaded['notebook']  # Projection saved together with evidence.
    resumed=[]
    result=p.run_batch(loaded,batch['id'],fake_call(restored,resumed),
                       _persist=lambda:c.save(loaded,path))
    assert calls==['quick_grading'] and resumed==['error_analysis']
    assert result['status']=='processed'
    assert c.load(path)['batches'][0]['status']=='processed'


def test_checkpoint_failure_stops_before_next_paid_step():
    w,batch,sub=workspace()
    saves=[]
    calls=[]
    def save():
        saves.append(1)
        if len(saves)==2:
            raise RuntimeError('磁盘无法写入')
    with pytest.raises(RuntimeError,match='磁盘'):
        p.run_batch(w,batch['id'],fake_call(sub,calls),_persist=save)
    assert calls==['quick_grading'] and not sub['analyses']


@pytest.mark.parametrize('strict',[False,True])
def test_runtime_storage_failure_is_fatal_only_for_paid_checkpoint(monkeypatch,strict):
    from ui import workbench
    runtime=workbench.Runtime.__new__(workbench.Runtime)
    runtime.w={'usage':[]}
    runtime.session='offline-storage-test'
    runtime.shared=False
    runtime.access=None
    warnings=[]
    monkeypatch.setattr(workbench,'for_session',lambda _:[])
    monkeypatch.setattr(workbench.st,'warning',warnings.append)
    def full_disk(_):raise OSError('synthetic disk failure')
    monkeypatch.setattr(workbench.store,'save',full_disk)
    if strict:
        with pytest.raises(RuntimeError,match='停止后续批改'):
            runtime.persist(strict=True)
        assert not warnings
    else:
        runtime.persist()
        assert len(warnings)==1


def test_transient_service_retries_then_succeeds_without_replaying_success():
    calls=[]
    waits=[]
    def provider():
        calls.append(1)
        if len(calls)<3:raise ServiceUnavailable('模拟网络故障')
        return 'ok'
    request=auto_resume(provider,lambda *args:None,sleep=waits.append)
    assert request()=='ok'
    assert len(calls)==3 and sum(waits)==6


def test_service_retry_and_total_wait_are_bounded():
    calls=[]
    def provider():
        calls.append(1)
        raise ServiceUnavailable('模拟网络故障')
    request=auto_resume(provider,lambda *args:None,sleep=lambda _:None,max_wait=20)
    with pytest.raises(ServiceUnavailable):request()
    assert len(calls)==3
    calls.clear()
    request=auto_resume(provider,lambda *args:None,sleep=lambda _:None,max_wait=3)
    with pytest.raises(ServiceUnavailable):request()
    assert len(calls)==2


@pytest.mark.parametrize('reason',['daily','disabled','provider_configuration','service'])
def test_nontransient_limit_never_retries_even_with_delay(reason):
    calls=[]
    def provider():
        calls.append(1)
        raise UsageLimitError('不可自动恢复',retry_after=1,reason=reason)
    request=auto_resume(provider,lambda *args:pytest.fail('Unexpected countdown'),
                        sleep=lambda _:pytest.fail('Unexpected wait'))
    with pytest.raises(UsageLimitError):request()
    assert len(calls)==1
