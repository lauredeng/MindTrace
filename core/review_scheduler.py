"""Official Py-FSRS adapter: scheduling is distinct from mathematical mastery."""
from copy import deepcopy
from datetime import datetime, timezone
from importlib.metadata import version
from uuid import uuid4
from fsrs import Card, Rating, Scheduler
from core import classroom as c, learning_records as learning

CONFIG=Scheduler(desired_retention=0.9,enable_fuzzing=False).to_dict()
VERSION='fsrs-'+version('fsrs')+'-policy-1'


def utc(value=None):
    value=value or datetime.now(timezone.utc)
    if value.tzinfo is None:raise ValueError('复习时间必须包含时区。')
    return value.astimezone(timezone.utc)


def add_unit(w,submission_id,student_id,*,objective='独立重做',when=None):
    learning.ensure(w)
    sub=learning.owned_submission(w,submission_id,student_id)
    if objective not in ('独立重做','关键条件回忆','关键步骤重建'):raise ValueError('复习目标无效。')
    existing=next((u for u in w['review_units'] if u['student_id']==student_id and
        u['submission_id']==submission_id and u['objective']==objective and learning.current(sub,u)),None)
    if existing:return existing
    card_id=uuid4().int & ((1<<63)-1)
    while any(u['initial_card']['card_id']==card_id for u in w['review_units']):card_id=uuid4().int & ((1<<63)-1)
    card=Card(card_id=card_id,due=utc(when))
    row=dict(id=c.uid(),student_id=student_id,submission_id=submission_id,objective=objective,
        initial_card=card.to_dict(),scheduler_config=deepcopy(CONFIG),scheduler_version=VERSION,
        material_fingerprint=sub['fingerprint'],reference_revision=sub.get('reference_revision'),created_at=c.now())
    row['grading_revision']=sub.get('grading_revision')
    w['review_units'].append(row)
    return row


def state(w,unit):
    sub=learning.owned_submission(w,unit['submission_id'],unit['student_id'])
    card=Card.from_dict(unit['initial_card']);scheduler=Scheduler.from_dict(unit['scheduler_config'])
    if not learning.current(sub,unit):return dict(card=card,stale=True,valid_reviews=0)
    count=0;attempts={a['id']:a for a in w.get('correction_attempts',[])}
    events=sorted([r for r in w.get('review_events',[]) if r['unit_id']==unit['id']],key=lambda r:(r['reviewed_at'],r['id']))
    for record in events:
        attempt=attempts.get(record['attempt_id'])
        assessment=learning.latest_assessment(w,attempt) if attempt else None
        if not assessment or assessment['id']!=record['assessment_id'] or assessment['method']=='ai':continue
        card,_=scheduler.review_card(card,Rating(record['rating']),review_datetime=datetime.fromisoformat(record['reviewed_at']),review_duration=record['duration_ms'])
        count+=1
    return dict(card=card,stale=False,valid_reviews=count)


def record_review(w,unit_id,student_id,attempt_id,rating,*,command_id,duration_ms=None,when=None):
    learning.ensure(w)
    if type(rating) is not int or rating not in (1,2,3,4):raise ValueError('请选择有效的复习难度。')
    if duration_ms is not None and (type(duration_ms) is not int or not 0<=duration_ms<=86400000):raise ValueError('复习耗时无效。')
    unit=next((u for u in w['review_units'] if u['id']==unit_id and u['student_id']==student_id),None)
    if unit is None:raise ValueError('只能更新自己的复习计划。')
    existing=next((r for r in w['review_events'] if r['student_id']==student_id and r['command_id']==command_id),None)
    if existing:
        if (existing['unit_id'],existing['attempt_id'],existing['rating'])!=(unit_id,attempt_id,rating):raise ValueError('同一复习命令不能用于不同作答。')
        return existing
    if any(r['unit_id']==unit_id and r['attempt_id']==attempt_id for r in w['review_events']):raise ValueError('这次作答已经更新过复习计划。')
    attempt=next((a for a in w['correction_attempts'] if a['id']==attempt_id and a['student_id']==student_id and a['submission_id']==unit['submission_id']),None)
    assessment=learning.latest_assessment(w,attempt) if attempt else None
    if not assessment or assessment['method']=='ai' or assessment['verdict']=='uncertain':raise ValueError('请先取得参考答案核验或教师复核结果，再更新复习计划。')
    if rating>1 and (assessment['verdict']!='correct' or not attempt['independent']):raise ValueError('只有独立完成且核验正确，才能记录为回忆成功。使用提示后请再独立尝试。')
    if rating==1 and assessment['verdict']=='correct' and attempt['independent']:raise ValueError('当前作答已独立完成，请选择相应的完成难度。')
    previous=state(w,unit)
    if previous['stale']:raise ValueError('题目已更新，请基于新版重新建立复习计划。')
    reviewed=utc(when)
    if previous['card'].last_review and reviewed<=previous['card'].last_review:raise ValueError('复习时间必须晚于上一条记录。')
    card,log=Scheduler.from_dict(unit['scheduler_config']).review_card(previous['card'],Rating(rating),review_datetime=reviewed,review_duration=duration_ms)
    row=dict(id=c.uid(),unit_id=unit_id,student_id=student_id,submission_id=unit['submission_id'],attempt_id=attempt_id,
        assessment_id=assessment['id'],rating=rating,command_id=command_id,reviewed_at=reviewed.isoformat(),created_at=c.now(),
        duration_ms=duration_ms,review_log=log.to_dict(),card_after=card.to_dict(),scheduler_version=VERSION,
        material_fingerprint=unit['material_fingerprint'],reference_revision=unit.get('reference_revision'))
    row['grading_revision']=unit.get('grading_revision')
    w['review_events'].append(row)
    return row


def due(w,student_id,*,when=None):
    learning.ensure(w);now=utc(when);output=[]
    for unit in w['review_units']:
        if unit['student_id']!=student_id:continue
        current=state(w,unit)
        if not current['stale'] and current['card'].due<=now:output.append(dict(unit=unit,due=current['card'].due,valid_reviews=current['valid_reviews']))
    return sorted(output,key=lambda row:row['due'])
