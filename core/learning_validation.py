"""Validate additive learning collections on save, import and student mutation."""
from core.records import _text


def validate_learning(w):
    subs={s['id']:s for s in w['submissions']}
    attempts={a['id']:a for a in w.get('correction_attempts',[])}
    units={u['id']:u for u in w.get('review_units',[])}
    assessments={a['id']:a for a in w.get('correction_reviews',[])}
    for key in ('correction_attempts','correction_reviews','learning_events','review_units','review_events'):
        for row in w.get(key,[]):
            sub=subs.get(row.get('submission_id'))
            if sub is None or row.get('student_id')!=sub['student_id']:
                raise ValueError('学习记录必须关联同一学生的有效题目。')
            _text(row.get('created_at'),100,'学习记录时间')
            if key=='correction_attempts':
                _text(row.get('answer'),2000,'订正答案',True)
                steps=row.get('steps')
                if not isinstance(steps,list) or len(steps)>30 or any(not isinstance(s,str) or len(s)>2000 for s in steps) or sum(map(len,steps))>8000:
                    raise ValueError('订正过程格式无效。')
                import re
                refs=row.get('attachment_refs',[])
                if not isinstance(refs,list) or len(refs)>12 or any(not isinstance(ref,str) or not re.fullmatch(r'[a-f0-9]{64}',ref) for ref in refs):
                    raise ValueError('订正附件引用无效。')
                if not steps and not row['answer'] and not refs:raise ValueError('订正不能是空白。')
                if any(type(row.get(k)) is not bool for k in ('independent','hint_used','answer_revealed')):
                    raise ValueError('订正独立性记录无效。')
                if row['independent'] and (row['hint_used'] or row['answer_revealed']):
                    raise ValueError('使用提示或答案后不能记为独立完成。')
            if key=='correction_reviews':
                attempt=attempts.get(row.get('attempt_id'))
                if not attempt or attempt['student_id']!=row['student_id'] or attempt['submission_id']!=row['submission_id']:
                    raise ValueError('订正复核没有关联有效作答。')
                if row.get('verdict') not in ('correct','incorrect','uncertain') or row.get('method') not in ('teacher','ai','reference_comparison'):
                    raise ValueError('订正复核结论无效。')
                _text(row.get('note'),2000,'订正反馈')
            if key=='review_events':
                unit=units.get(row.get('unit_id'))
                if not unit or unit['student_id']!=row['student_id'] or unit['submission_id']!=row['submission_id']:
                    raise ValueError('复习记录没有关联自己的复习计划。')
                assessment=assessments.get(row.get('assessment_id'))
                attempt=attempts.get(row.get('attempt_id'))
                if (not assessment or not attempt or assessment['attempt_id']!=attempt['id'] or
                    attempt['submission_id']!=row['submission_id'] or assessment.get('method')=='ai'):
                    raise ValueError('复习记录缺少可靠核验来源。')
                rating=row.get('rating')
                if type(rating) is not int or not 1<=rating<=4:raise ValueError('复习评分无效。')
                if rating>1 and (not attempt['independent'] or assessment['verdict']!='correct'):
                    raise ValueError('未独立完成的作答不能记为回忆成功。')
            if key=='review_units':
                from core.review_scheduler import CONFIG
                from fsrs import Card
                if row.get('scheduler_config')!=CONFIG:raise ValueError('复习调度配置无效。')
                try:card=Card.from_dict(row['initial_card'])
                except (KeyError,TypeError,ValueError):raise ValueError('复习卡片格式无效。') from None
                if card.stability is not None or card.difficulty is not None or card.last_review is not None:
                    raise ValueError('新复习计划不能预设历史学习状态。')
