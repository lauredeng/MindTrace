"""Append-only corrections and evidence projections; no inferred ability scores."""
from copy import deepcopy
from core import classroom as c, education as e, product as p

COLLECTIONS=('correction_attempts','correction_reviews','learning_events','review_units','review_events')


def ensure(w):
    for key in COLLECTIONS:w.setdefault(key,[])


def owned_submission(w,submission_id,student_id):
    sub=next((s for s in w['submissions'] if s['id']==submission_id and s['student_id']==student_id),None)
    if sub is None:raise ValueError('只能操作自己的作答。')
    return sub


def current(sub,record):
    return record.get('material_fingerprint')==sub['fingerprint'] and record.get('reference_revision')==sub.get('reference_revision') and record.get('grading_revision')==sub.get('grading_revision')


def event(w,student_id,submission_id,kind,source_id,**data):
    ensure(w)
    sub=owned_submission(w,submission_id,student_id)
    key=p.digest([student_id,submission_id,kind,source_id,sub['fingerprint'],sub.get('reference_revision')])
    previous=next((x for x in w['learning_events'] if x['event_key']==key),None)
    if previous:return previous
    row=dict(id=c.uid(),event_key=key,student_id=student_id,submission_id=submission_id,kind=kind,
             source_id=source_id,created_at=c.now(),material_fingerprint=sub['fingerprint'],
             grading_revision=sub.get('grading_revision'),
             reference_revision=sub.get('reference_revision'),data=deepcopy(data))
    w['learning_events'].append(row)
    return row


def submit_correction(w,submission_id,student_id,steps,answer,*,command_id,independent=True,
                      hint_used=False,answer_revealed=False,origin='correction',parent_id=None,attachment_refs=None):
    ensure(w)
    sub=owned_submission(w,submission_id,student_id)
    if origin not in ('correction','review'):raise ValueError('作答来源无效。')
    if any(type(x) is not bool for x in (independent,hint_used,answer_revealed)):
        raise ValueError('请明确作答是否使用提示或参考答案。')
    command_id=e.text(command_id,100,'提交编号')
    import re
    attachments=list(attachment_refs or [])
    if len(attachments)>12 or any(not isinstance(ref,str) or not re.fullmatch(r'[a-f0-9]{64}',ref) for ref in attachments):
        raise ValueError('订正附件引用无效。')
    normalized=e.normalize_submission(dict(sub,steps=steps,answer=answer),allow_unanswered=bool(attachments))
    payload=p.digest([submission_id,normalized['steps'],normalized['answer'],independent,hint_used,answer_revealed,origin,parent_id,attachments])
    existing=next((a for a in w['correction_attempts'] if a['student_id']==student_id and a['command_id']==command_id),None)
    if existing:
        if existing['payload_hash']!=payload:raise ValueError('同一提交编号不能用于不同作答。')
        return existing
    if parent_id and not any(a['id']==parent_id and a['student_id']==student_id and a['submission_id']==submission_id for a in w['correction_attempts']):
        raise ValueError('订正必须关联自己的同一道题。')
    row=dict(id=c.uid(),student_id=student_id,submission_id=submission_id,command_id=command_id,
             steps=normalized['steps'],answer=normalized['answer'],origin=origin,parent_id=parent_id,
             independent=independent and not hint_used and not answer_revealed,hint_used=hint_used,
             answer_revealed=answer_revealed,created_at=c.now(),payload_hash=payload,
             attachment_refs=attachments,
             grading_revision=sub.get('grading_revision'),
             material_fingerprint=sub['fingerprint'],reference_revision=sub.get('reference_revision'))
    def apply(draft):
        draft['correction_attempts'].append(row)
        event(draft,student_id,submission_id,'attempt_submitted',row['id'],origin=origin)
    c.commit(w,'correction-'+student_id+'-'+command_id,apply)
    return next(a for a in w['correction_attempts'] if a['id']==row['id'])


def assess_correction(w,attempt_id,verdict,note,*,command_id,method='teacher'):
    ensure(w)
    if verdict not in e.VERDICTS:raise ValueError('订正判定无效。')
    if method not in ('teacher','reference_comparison','ai'):raise ValueError('核验来源无效。')
    note=e.text(note,2000,'订正反馈')
    attempt=next(a for a in w['correction_attempts'] if a['id']==attempt_id)
    sub=owned_submission(w,attempt['submission_id'],attempt['student_id'])
    if not current(sub,attempt):raise ValueError('题目或参考答案已更新，请学生基于新版重新订正。')
    existing=next((r for r in w['correction_reviews'] if r['command_id']==command_id),None)
    if existing:
        if (existing['attempt_id'],existing['verdict'],existing['note'])!=(attempt_id,verdict,note):
            raise ValueError('复核命令已用于不同结果。')
        return existing
    row=dict(id=c.uid(),attempt_id=attempt_id,submission_id=sub['id'],student_id=sub['student_id'],
             verdict=verdict,note=note,method=method,command_id=command_id,created_at=c.now(),
             material_fingerprint=sub['fingerprint'],reference_revision=sub.get('reference_revision'))
    row['grading_revision']=sub.get('grading_revision')
    def apply(draft):
        draft['correction_reviews'].append(row)
        event(draft,sub['student_id'],sub['id'],'attempt_assessed',row['id'],attempt_id=attempt_id,verdict=verdict,method=method)
    c.commit(w,'correction-review-'+command_id,apply)
    return next(r for r in w['correction_reviews'] if r['id']==row['id'])


def latest_assessment(w,attempt):
    sub=owned_submission(w,attempt['submission_id'],attempt['student_id'])
    if not current(sub,attempt):return None
    return next((r for r in reversed(w.get('correction_reviews',[])) if r['attempt_id']==attempt['id'] and current(sub,r)),None)


def compare_correction(w,attempt_id):
    attempt=next(a for a in w['correction_attempts'] if a['id']==attempt_id)
    sub=owned_submission(w,attempt['submission_id'],attempt['student_id'])
    batch=next((b for b in w['batches'] if b['id']==sub.get('batch_id')),None)
    reference=next((entry['confirmed'] for entry in (batch or {}).get('answer_keys',{}).values()
        if entry.get('confirmed',{}).get('id')==sub.get('reference_revision')),None)
    material=dict(sub,steps=attempt['steps'],answer=attempt['answer'],submission_status='submitted')
    matched=p.reference_match(material,reference) if reference else None
    if matched is None:return {'comparable':False}
    return {'comparable':True,'assessment':assess_correction(w,attempt_id,'correct' if matched else 'incorrect',
        '按教师已确认的参考答案核对最终答案。',command_id=c.uid(),method='reference_comparison')}


def correction_progress(w,submission_id,student_id):
    sub=owned_submission(w,submission_id,student_id)
    attempt=next((a for a in reversed(w.get('correction_attempts',[])) if a['submission_id']==submission_id and
                  a['student_id']==student_id and current(sub,a)),None)
    if attempt is None:return None
    assessment=latest_assessment(w,attempt)
    if not assessment or assessment['verdict']=='uncertain':state,label='pending','订正待复核'
    elif assessment['verdict']=='incorrect':state,label='incorrect','仍需订正'
    elif attempt['independent']:state,label='independent','已独立订正'
    else:state,label='assisted','订正通过 · 待独立验证'
    return dict(state=state,label=label,attempt_id=attempt['id'],assessment_id=(assessment or {}).get('id'))


def profile(w,student_id):
    """Recomputed from current evidence: invalidated references disappear immediately."""
    ensure(w)
    records=[s for s in w['submissions'] if s['student_id']==student_id]
    points={}
    for sub in records:
        state=p.effective(w,sub)
        q=p.latest(sub,'quick_checks') or {}
        teacher=c.latest_review(w,sub['id'])
        labels=(teacher.get('knowledge_points') if teacher and state['confirmed']
                and state['source_id']==teacher['id'] else q.get('knowledge_points')) or [sub['topic']]
        for label in labels:
            row=points.setdefault(label,dict(label=label,original_correct=0,original_incorrect=0,
                                            unconfirmed=0,independent_success=0,assisted_success=0,evidence=[]))
            if state['confirmed'] and state['verdict'] in ('correct','incorrect'):
                row['original_'+state['verdict']]+=1
            else:row['unconfirmed']+=1
            row['evidence'].append(dict(submission_id=sub['id'],source_id=state['source_id'],kind='original',
                                        confirmed=state['confirmed'],verdict=state['verdict']))
            for attempt in w['correction_attempts']:
                if attempt['submission_id']!=sub['id'] or attempt['student_id']!=student_id:continue
                assessment=latest_assessment(w,attempt)
                if not assessment or assessment['method']=='ai':continue
                if assessment['verdict']=='correct':
                    row['independent_success' if attempt['independent'] else 'assisted_success']+=1
                row['evidence'].append(dict(submission_id=sub['id'],source_id=assessment['id'],attempt_id=attempt['id'],
                                            kind=attempt['origin'],verdict=assessment['verdict'],independent=attempt['independent']))
    # Top-level exercises and Agent-nested exercises share the same projection.
    # Legacy attempts without material provenance remain history, not new facts.
    practices=list(w.get('attempts',[]))
    for session in w.get('study_sessions',[]):
        if session['student_id']!=student_id:continue
        for run in session.get('agent_runs',[]):practices.extend(run.get('practice',{}).get('attempts',[]))
    seen=set()
    for attempt in practices:
        if attempt.get('student_id')!=student_id or attempt['id'] in seen:continue
        seen.add(attempt['id'])
        sub=next((s for s in records if s['id']==attempt.get('submission_id')),None)
        if not sub or not current(sub,attempt):continue
        for label in attempt.get('knowledge_points') or [sub['topic']]:
            row=points.setdefault(label,dict(label=label,original_correct=0,original_incorrect=0,unconfirmed=0,
                                            independent_success=0,assisted_success=0,evidence=[]))
            verified=attempt.get('independently_verified') and not attempt.get('conflict')
            if attempt['verdict']=='correct' and verified:
                row['independent_success' if attempt.get('independent') else 'assisted_success']+=1
            row['evidence'].append(dict(submission_id=sub['id'],source_id=attempt['id'],attempt_id=attempt['id'],
                kind='transfer',verdict=attempt['verdict'] if verified else 'uncertain',independent=attempt.get('independent',False),
                question=attempt.get('exercise_question','')))
    return {'student_id':student_id,'points':list(points.values()),
            'valid_events':[deepcopy(x) for x in w['learning_events'] if x['student_id']==student_id and
                            any(s['id']==x['submission_id'] and current(s,x) for s in records)],
            'limitation':'记录反映具体题目的作答证据，不等同于综合能力或长期掌握率。'}


def recall(w,student_id,*,exclude_submission=None,limit=6):
    """Small cross-question memory with visible, current source references."""
    projection=profile(w,student_id)
    evidence=[]
    for row in projection['points']:
        for source in row['evidence']:
            if source['submission_id']==exclude_submission or not source.get('source_id'):continue
            if source['kind']=='original' and not source['confirmed']:continue
            evidence.append(dict(knowledge_point=row['label'],**source))
    return evidence[-limit:]
