"""Real classroom, official FSRS and current evidence across the new UI boundary."""
import pytest
from core import tutor_learning as ui,learning_records as learning,review_scheduler as fsrs
from test_tutor_bridge import bridge_case,login


def start(case):
    store,teacher,codes,w=case
    binding,_=login(store,codes[0]);sid=w['submissions'][0]['id']
    unit=ui.add_review(binding,sid)
    return store,binding,unit,ui.start_review(store,binding,unit['id'])


def confirm(binding,attempt_id):
    ui.mutate(binding,lambda w:learning.assess_correction(w,attempt_id,'correct','教师核对过程与结论。',command_id='teacher-'+attempt_id))


def test_review_starts_without_answer_and_rejects_peer_and_unverified_rating(bridge_case):
    store,binding,unit,run=start(bridge_case)
    assert set(run)=={'run_id','question','unit_id','submission_id','objective'}
    peer,_=login(store,bridge_case[2][1])
    with pytest.raises(ValueError):ui.submit_review(store,peer,run['run_id'],[],'1/x-2')
    result=ui.submit_review(store,binding,run['run_id'],['求导保留线性项'],'1/x-2')
    assert result['independent'] and not result['can_rate']
    with pytest.raises(ValueError):ui.rate_review(store,binding,run['run_id'],result['attempt_id'],3)
    assert not ui.workspace(binding)['review_events']


def test_teacher_feedback_then_actual_fsrs_schedule_and_idempotent_replay(bridge_case):
    store,binding,unit,run=start(bridge_case)
    attempt=ui.submit_review(store,binding,run['run_id'],['求导'],'1/x-2')
    confirm(binding,attempt['attempt_id'])
    refreshed=ui.review_result(store,binding,run['run_id'])
    assert refreshed['can_recall_success']
    assert ui.reviews(binding,store)[0]['pending_run_id']==run['run_id']
    schedule=ui.rate_review(store,binding,run['run_id'],attempt['attempt_id'],3)
    assert schedule['scheduler_version']==fsrs.VERSION
    assert ui.rate_review(store,binding,run['run_id'],attempt['attempt_id'],3)==schedule
    assert ui.reviews(binding,store)[0]['valid_reviews']==1
    assert ui.reviews(binding,store)[0]['pending_run_id'] is None
    with pytest.raises(ValueError):ui.rate_review(store,binding,run['run_id'],attempt['attempt_id'],4)


def test_server_observed_help_cannot_be_claimed_as_independent(bridge_case):
    store,binding,unit,run=start(bridge_case)
    store.mark_assisted(binding['id'],run['submission_id'])
    result=ui.submit_review(store,binding,run['run_id'],['求导'],'1/x-2',helped=False)
    assert not result['independent']
    confirm(binding,result['attempt_id'])
    assert not ui.review_result(store,binding,run['run_id'])['can_recall_success']
    with pytest.raises(ValueError):ui.rate_review(store,binding,run['run_id'],result['attempt_id'],3)
    assert ui.rate_review(store,binding,run['run_id'],result['attempt_id'],1)['rating']==1


def test_changed_reference_invalidates_active_run_and_cross_run_attempt_rejected(bridge_case):
    store,binding,unit,run=start(bridge_case)
    attempt=ui.submit_review(store,binding,run['run_id'],['求导'],'1/x-2')
    other=ui.start_review(store,binding,unit['id'])
    with pytest.raises(ValueError):ui.rate_review(store,binding,other['run_id'],attempt['attempt_id'],3)
    def change(w):w['submissions'][0]['reference_revision']='new-teacher-reference'
    ui.mutate(binding,change)
    with pytest.raises(ValueError):ui.submit_review(store,binding,run['run_id'],['求导'],'1/x-2')
    with pytest.raises(ValueError):ui.review_result(store,binding,run['run_id'])
    assert ui.reviews(binding,store)[0]['stale']


def test_help_after_saved_attempt_does_not_rewrite_independence_or_allow_changed_answer(bridge_case):
    store,binding,unit,run=start(bridge_case)
    first=ui.submit_review(store,binding,run['run_id'],['求导'],'1/x-2')
    store.mark_assisted(binding['id'],run['submission_id'])
    replay=ui.submit_review(store,binding,run['run_id'],['求导'],'1/x-2')
    assert first==replay and replay['independent']
    with pytest.raises(ValueError):ui.submit_review(store,binding,run['run_id'],['求导'],'another answer')


def test_pending_review_not_attached_to_another_objective(bridge_case):
    store,binding,unit,run=start(bridge_case)
    other=ui.add_review(binding,run['submission_id'],'关键步骤重建')
    ui.submit_review(store,binding,run['run_id'],['求导'],'1/x-2')
    rows={r['unit_id']:r for r in ui.reviews(binding,store)}
    assert rows[unit['id']]['pending_run_id']==run['run_id']
    assert rows[other['id']]['pending_run_id'] is None


def test_profile_uses_teacher_confirmed_knowledge_point_labels(bridge_case):
    from core import classroom as c
    store,binding,unit,run=start(bridge_case)
    def confirm_original(w):
        from core import education
        from test_education import report
        sub=next(s for s in w['submissions'] if s['id']==run['submission_id'])
        education.analyze_submission(sub,lambda *a,**kw:report(sub,1))
        c.review(w,run['submission_id'],'confirm','求导漏项',['线性项求导'],
                 '求导时需要保留常数系数。','teacher-label-correction')
    ui.mutate(binding,confirm_original)
    assert [p['label'] for p in learning.profile(ui.workspace(binding),binding['student_id'])['points']]==['线性项求导']
