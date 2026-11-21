"""Integration contracts: durable tasks, real FSRS and evidence invalidation."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import json

import pytest
from fsrs import Card,Rating,Scheduler
from core import classroom as c,product as p,presentation as v,identities,learning_records as l,review_scheduler as review
from core.repository import Repository,ConflictError
from core.background import Worker
from core.limits import UsageLimitError


def setup_work(rows=None):
    w=c.new_workspace()
    rows=rows or [dict(student_id='001',question='选择正确选项。A 正确；B 错误；C 正确。',
                       question_no='1',question_type='多选题',answer='A')]
    b=p.create_batch(w,'周练',rows,grading_policy=p.CLASSROOM_POLICY)
    return w,b,w['submissions'][0]


def assess(w,sub,*,independent=True,verdict='correct',command='one'):
    a=l.submit_correction(w,sub['id'],sub['student_id'],[],'AC',command_id=command,independent=independent,hint_used=not independent)
    r=l.assess_correction(w,a['id'],verdict,'核对完整选项集合。',command_id='review-'+command)
    return a,r


def test_identity_punctuation_is_safe_but_math_and_labels_are_not_erased():
    rows=[dict(student_id=s,question=q,question_no='1',answer='1',question_type='填空题') for s,q in
          [('001','求 x 的值。'),('002','求x的值'),('003','求 -x 的值。')]]
    w,b,a=setup_work(rows)
    assert a['assignment_question_id']==w['submissions'][1]['assignment_question_id']
    assert a['assignment_question_id']!=w['submissions'][2]['assignment_question_id']
    assert len(v.heatmap_rows(w,b['id']))==2
    before=deepcopy(b);identities.attach(b,w['submissions']);assert b==before


def test_roster_is_assignment_snapshot_and_absence_is_separate():
    w=c.new_workspace();w['student_roster']=['001','002','003']
    b=p.create_batch(w,'周练',[dict(student_id='001',question='x=1?',answer='1')])
    w['student_roster'].append('004')
    assert identities.assignment_counts(w,b)['missing']==['002','003']
    row=v.heatmap_rows(w,b['id'],automatic=True)[0]
    assert row['errors']==0 and row['missing']==2


def test_choices_all_share_local_set_comparison_and_single_rejects_multi_key():
    from core.answer_keys import compare,validated
    assert compare('多选题','C、A','AC') is True
    assert compare('多选题','A','AC') is False
    assert compare('多选题','ABC','AC') is False
    assert compare('单选题','AB','A') is False
    _,_,sub=setup_work();sub['question_type']='单选题'
    with pytest.raises(ValueError):validated(sub,'AC','')


def test_corrections_are_owned_append_only_and_idempotent():
    w,b,sub=setup_work();original=deepcopy(sub)
    a,r=assess(w,sub)
    assert w['submissions'][0]==original
    assert l.submit_correction(w,sub['id'],'001',[],'AC',command_id='one')['id']==a['id']
    with pytest.raises(ValueError):l.submit_correction(w,sub['id'],'OTHER',[],'AC',command_id='x')
    with pytest.raises(ValueError):l.submit_correction(w,sub['id'],'001',[],'B',command_id='one')
    assert len(w['learning_events'])==2
    c.validate_workspace(w)


def test_profile_sources_invalidate_after_reference_or_teacher_assessment_change():
    w,b,sub=setup_work();a,r=assess(w,sub)
    assert l.profile(w,'001')['points'][0]['independent_success']==1
    l.assess_correction(w,a['id'],'incorrect','更正此前复核。',command_id='changed')
    assert l.profile(w,'001')['points'][0]['independent_success']==0
    w['submissions'][0]['reference_revision']='changed-reference'
    assert l.latest_assessment(w,a) is None
    assert l.profile(w,'001')['valid_events']==[]


@pytest.mark.parametrize('rating,verdict,independent',[(1,'incorrect',False),(2,'correct',True),(3,'correct',True),(4,'correct',True)])
def test_official_fsrs_roundtrip_replay_and_idempotence(rating,verdict,independent):
    w,b,sub=setup_work();a,r=assess(w,sub,verdict=verdict,independent=independent)
    now=datetime(2026,11,21,3,tzinfo=timezone.utc)
    u=review.add_unit(w,sub['id'],'001',when=now)
    event=review.record_review(w,u['id'],'001',a['id'],rating,command_id='rate',duration_ms=30000,when=now)
    expected,_=Scheduler.from_dict(u['scheduler_config']).review_card(Card.from_dict(u['initial_card']),Rating(rating),review_datetime=now,review_duration=30000)
    restored=json.loads(json.dumps(w))
    assert review.state(restored,u)['card'].to_dict()==expected.to_dict()
    assert review.record_review(w,u['id'],'001',a['id'],rating,command_id='rate',when=now)==event
    assert len(w['review_events'])==1
    with pytest.raises(ValueError):review.record_review(w,u['id'],'001',a['id'],rating,command_id='again',when=now)


def test_assisted_or_unconfirmed_work_never_becomes_successful_recall():
    w,b,sub=setup_work();a,r=assess(w,sub,independent=False)
    unit=review.add_unit(w,sub['id'],'001')
    with pytest.raises(ValueError):review.record_review(w,unit['id'],'001',a['id'],3,command_id='bad')
    w['submissions'][0]['fingerprint']='changed-material'
    assert review.state(w,unit)['stale']
    assert not review.due(w,'001')


def test_sqlite_version_conflicts_pagination_and_idempotent_migration(tmp_path):
    w,b,s=setup_work();repo=Repository(tmp_path/'test.db')
    source=tmp_path/'source.json';source.write_text(json.dumps([w]),encoding='utf-8')
    assert repo.import_json(source)==repo.import_json(source)==w['id']
    current=repo.load(workspace_id=w['id']);stale=deepcopy(current)
    repo.save(current,str(source.resolve()))
    with pytest.raises(ConflictError):repo.save(stale,str(source.resolve()))
    assert repo.query_records(w['id'],'submissions',student_id='001')[0]['id']==s['id']
    assert not repo.query_records(w['id'],'submissions',student_id='OTHER')
    restored=Repository(repo.backup(tmp_path/'backup.db'))
    assert restored.load(workspace_id=w['id'])==repo.load(workspace_id=w['id'])


def test_atomic_claim_fencing_cancellation_and_late_result(tmp_path):
    now=[1000.0];repo=Repository(tmp_path/'tasks.db',clock=lambda:now[0]);w,b,s=setup_work()
    repo.save(w,'class');repo.enqueue_batch(w['id'],b['id'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims=list(pool.map(lambda i:repo.claim(str(i),lease_seconds=2),range(4)))
    first=next(j for j in claims if j)
    assert len([j for j in claims if j])==1
    now[0]+=3;second=repo.claim('new')
    assert second['fence']>first['fence']
    record=p.quick_check(deepcopy(s),lambda *a,**k:dict(verdict='correct',process_checked=False,basis='样例核对'))
    assert repo.finish(first,record) is False
    repo.cancel_batch(w['id'],b['id'])
    assert repo.finish(second,record) is False
    assert not repo.load(workspace_id=w['id'])['submissions'][0]['quick_checks']


def test_background_worker_finishes_after_ui_is_gone_and_survives_restart(tmp_path):
    repo=Repository(tmp_path/'worker.db');w,b,s=setup_work();repo.save(w,'class')
    repo.enqueue_batch(w['id'],b['id']);calls=[]
    def model(*args,**kwargs):
        calls.append(kwargs['purpose']);return dict(verdict='correct',process_checked=False,basis='完整集合核对')
    assert Worker(Repository(repo.path),model).tick()
    assert repo.jobs(w['id'],b['id'])[0]['status']=='completed'
    assert repo.load(workspace_id=w['id'])['submissions'][0]['quick_checks'][-1]['verdict']=='correct'
    assert repo.enqueue_batch(w['id'],b['id'])==0
    assert not Worker(Repository(repo.path),model).tick()
    assert calls==['quick_grading']


def test_background_wait_is_persisted_not_ui_sleep_and_quota_survives_restart(tmp_path):
    now=[1000.0];repo=Repository(tmp_path/'limits.db',clock=lambda:now[0]);w,b,s=setup_work();repo.save(w,'class')
    repo.enqueue_batch(w['id'],b['id'])
    def limited(*a,**k):raise UsageLimitError('稍后恢复',reason='provider',retry_after=10)
    Worker(repo,limited).tick()
    assert repo.jobs(w['id'],b['id'])[0]['status']=='retry_wait'
    assert repo.claim('early') is None
    now[0]+=11;job=repo.claim('restarted')
    assert job['attempts']==2
    with pytest.raises(UsageLimitError):Repository(repo.path,clock=lambda:now[0]).admit(job['id'],1,daily=1)


def test_teacher_review_during_model_request_wins(tmp_path):
    repo=Repository(tmp_path/'race.db');w,b,s=setup_work();repo.save(w,'class');repo.enqueue_batch(w['id'],b['id'])
    def model(*a,**k):
        repo.mutate(w['id'],lambda state:v.override_grade(state,s['id'],'incorrect','教师先完成了复核。'))
        return dict(verdict='correct',process_checked=False,basis='晚到的样例响应')
    Worker(repo,model).tick()
    saved=repo.load(workspace_id=w['id'])
    assert p.effective(saved,saved['submissions'][0])['verdict']=='incorrect'
    assert repo.jobs(w['id'],b['id'])[0]['status']=='stale'


def test_persisted_concurrency_reservation_blocks_second_process_then_releases(tmp_path):
    repo=Repository(tmp_path/'concurrency.db')
    w,b,s=setup_work([dict(student_id=sid,question='选出正确项：A正确，B错误。',question_type='单选题',answer='A') for sid in ('001','002')])
    repo.save(w,'class');repo.enqueue_batch(w['id'],b['id'])
    first=repo.claim('one');second=repo.claim('two')
    token=repo.admit(first['id'],10,concurrent=1)
    with pytest.raises(UsageLimitError) as error:Repository(repo.path).admit(second['id'],10,concurrent=1)
    assert error.value.reason=='busy'
    repo.settle(token,'completed')
    assert Repository(repo.path).admit(second['id'],10,concurrent=1)


def test_review_projection_rebuilds_after_teacher_revokes_old_assessment():
    w,b,s=setup_work();a,r=assess(w,s)
    now=datetime(2026,11,21,3,tzinfo=timezone.utc)
    unit=review.add_unit(w,s['id'],'001',when=now)
    review.record_review(w,unit['id'],'001',a['id'],3,command_id='good',when=now)
    assert review.state(w,unit)['valid_reviews']==1
    l.assess_correction(w,a['id'],'incorrect','更正此前判定。',command_id='revoke')
    assert review.state(w,unit)['valid_reviews']==0
    assert len(w['review_events'])==1  # Historical log remains auditable.


def test_notebook_learning_progress_tracks_correction_without_rewriting_original_grade():
    w,b,s=setup_work()
    a=l.submit_correction(w,s['id'],'001',[],'AC',command_id='notebook-correction')
    assert l.correction_progress(w,s['id'],'001')['state']=='pending'
    l.assess_correction(w,a['id'],'correct','订正已核对。',command_id='notebook-review')
    assert l.correction_progress(w,s['id'],'001')['state']=='independent'
    assert w['submissions'][0]['answer']=='A'
