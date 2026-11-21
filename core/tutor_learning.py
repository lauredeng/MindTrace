"""Classroom commands for the official student UI; reuse canonical FSRS and evidence."""
from core import classroom as c,collaboration as collab,learning_records as learning,review_scheduler as fsrs
from core.tutor_bridge import source


def workspace(binding):return c.load(collab._folder(binding['class_id'])/'workspace.json')


def mutate(binding,operation):
    from core.background import configured_repository
    from core.storage import LOCK
    path=collab._folder(binding['class_id'])/'workspace.json'
    repo=configured_repository()
    if repo:
        _,result=repo.mutate(c.load(path)['id'],operation)
        return result
    with LOCK:
        w=c.load(path);result=operation(w);c.save(w,path);return result


def reviews(binding,store=None):
    w=workspace(binding);learning.ensure(w);rows=[]
    for u in w['review_units']:
        if u['student_id']!=binding['student_id']:continue
        sub=learning.owned_submission(w,u['submission_id'],binding['student_id'])
        state=fsrs.state(w,u)
        def same_run(a):
            if store is None:return False
            try:
                run=store.review_run(binding['id'],a['command_id'][len('tutor-review-'):])
                return run['unit_id']==u['id']
            except ValueError:return False
        prior=next((a for a in reversed(w.get('correction_attempts',[])) if a['student_id']==binding['student_id']
            and a['submission_id']==sub['id'] and a['command_id'].startswith('tutor-review-')
            and same_run(a)
            and not any(e['attempt_id']==a['id'] and e['unit_id']==u['id'] for e in w.get('review_events',[]))),None)
        rows.append(dict(unit_id=u['id'],submission_id=sub['id'],question=sub['question'],
            objective=u['objective'],due=state['card'].due.isoformat(),stale=state['stale'],
            is_due=not state['stale'] and state['card'].due<=fsrs.utc(),valid_reviews=state['valid_reviews'],
            pending_run_id=prior['command_id'][len('tutor-review-'):] if prior else None))
    return sorted(rows,key=lambda r:(r['stale'],not r['is_due'],r['due']))


def add_review(binding,sid,objective='独立重做'):
    return mutate(binding,lambda w:fsrs.add_unit(w,sid,binding['student_id'],objective=objective))


def start_review(store,binding,unit_id):
    row=next((r for r in reviews(binding) if r['unit_id']==unit_id),None)
    if row is None or row['stale']:raise ValueError('复习题目不存在或依据已更新，请重新加入计划。')
    current=source(binding,row['submission_id'])
    run_id=store.start_review(binding['id'],unit_id,row['submission_id'],current['source_revision'])
    # Intentionally no original answer, feedback or reference in a recall screen.
    return dict(run_id=run_id,question=current['question'],unit_id=unit_id,
                submission_id=row['submission_id'],objective=row['objective'])


def submit_review(store,binding,run_id,steps,answer,*,helped=False):
    run=store.review_run(binding['id'],run_id)
    current=source(binding,run['submission_id'])
    if current['source_revision']!=run['revision']:raise ValueError('教师已更新题目依据，请重新开始。')
    def apply(w):
        if source(binding,run['submission_id'],w)['source_revision']!=run['revision']:
            raise ValueError('教师已更新题目依据，请重新开始。')
        command='tutor-review-'+run_id
        prior=next((a for a in w.get('correction_attempts',[]) if a['student_id']==binding['student_id'] and a['command_id']==command),None)
        assisted=bool(run['assisted'] or helped)
        # Reading feedback after submission cannot retrospectively change an
        # already-saved attempt. Replays still validate its answer and steps.
        flags=dict(independent=not assisted,hint_used=assisted,answer_revealed=bool(run['assisted']))
        if prior:flags={key:prior[key] for key in flags}
        attempt=learning.submit_correction(w,run['submission_id'],binding['student_id'],steps,answer,
            command_id=command,origin='review',**flags)
        if learning.latest_assessment(w,attempt) is None:learning.compare_correction(w,attempt['id'])
        assessment=learning.latest_assessment(w,attempt)
        eligible=bool(assessment and assessment['method']!='ai' and assessment['verdict']!='uncertain')
        return dict(attempt_id=attempt['id'],independent=attempt['independent'],assessment=assessment,
            can_rate=eligible,can_recall_success=eligible and attempt['independent'] and assessment['verdict']=='correct')
    return mutate(binding,apply)


def review_result(store,binding,run_id):
    run=store.review_run(binding['id'],run_id)
    w=workspace(binding)
    if source(binding,run['submission_id'])['source_revision']!=run['revision']:
        raise ValueError('题目依据已更新，请重新开始。')
    attempt=next((a for a in w.get('correction_attempts',[]) if a['student_id']==binding['student_id']
        and a['command_id']=='tutor-review-'+run_id),None)
    if attempt is None:raise ValueError('尚未提交本次复习作答。')
    assessment=learning.latest_assessment(w,attempt)
    eligible=bool(assessment and assessment['method']!='ai' and assessment['verdict']!='uncertain')
    return dict(attempt_id=attempt['id'],independent=attempt['independent'],assessment=assessment,
        can_rate=eligible,can_recall_success=bool(eligible and attempt['independent'] and assessment['verdict']=='correct'))


def rate_review(store,binding,run_id,attempt_id,rating):
    run=store.review_run(binding['id'],run_id)
    current=source(binding,run['submission_id'])
    if current['source_revision']!=run['revision']:raise ValueError('题目依据已更新，请重新开始。')
    def apply(w):
        if source(binding,run['submission_id'],w)['source_revision']!=run['revision']:
            raise ValueError('教师已更新题目依据，请重新开始。')
        attempt=next((a for a in w.get('correction_attempts',[]) if a['id']==attempt_id
            and a['student_id']==binding['student_id'] and a['command_id']=='tutor-review-'+run_id),None)
        if attempt is None:raise ValueError('请先提交本次复习作答。')
        event=fsrs.record_review(w,run['unit_id'],binding['student_id'],attempt_id,rating,
                                command_id='tutor-rating-'+run_id)
        return dict(due=event['card_after']['due'],rating=event['rating'],scheduler_version=event['scheduler_version'])
    return mutate(binding,apply)
