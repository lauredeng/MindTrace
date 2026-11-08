"""Presentation statistics: confirmed headcounts, exam hierarchy and notebook types."""
from collections import Counter
import math
import re
from copy import deepcopy
from core import product as p, education as e, classroom as c

TYPES=e.QUESTION_TYPES
UNKNOWN='未分类'

def kind(item):
    value=item.get('question_type_override',item.get('question_type',UNKNOWN))
    return value if value in TYPES else UNKNOWN

def hierarchy(item):
    parent=item.get('parent_question_no','')
    child=item.get('subquestion_no','')
    label=item.get('question_no','') or '未编号'
    if not parent:
        match=re.fullmatch(r'\s*(\d+)\s*[（(](\d+)[）)]\s*',label)
        if match:parent,child=match.groups()
    return parent,child,(parent+'('+child+')' if parent and child else label)

def record_state(w,sub,*,automatic=False):
    if automatic:
        manual=c.latest_review(w,sub['id'])
        if manual and manual.get('manual_grade') and manual.get('fingerprint')==sub['fingerprint'] and not p.is_blank(sub):
            return 'incorrect' if manual['is_error'] else 'correct'
    raw='\n'.join([sub['question'],*sub['steps'],sub['answer']])
    if sub.get('submission_status')=='unreadable' or '[无法辨认]' in raw:
        return 'unreadable'
    if sub.get('submission_status')=='not_submitted' or not (sub['steps'] or sub['answer']):
        return 'not_submitted'
    state=p.effective(w,sub)
    if (automatic or state['confirmed']) and state['verdict'] in ('correct','incorrect'):
        return state['verdict']
    return 'pending'

def sort_key(item):
    numbers=tuple(int(v) for v in re.findall(r'\d+',item['label']))
    return numbers or (999999,),item['label']

def heatmap_rows(w,batch_id,*,automatic=False):
    batch=next(b for b in w['batches'] if b['id']==batch_id)
    subs={s['id']:s for s in w['submissions']}
    chosen={}
    for sid in batch['submission_ids']:
        sub=subs.get(sid)
        if sub:chosen[(p.item_key(sub),sub['student_id'])]=sub
    questions={q['id']:q for q in batch['questions']}
    for (qid,_),sub in chosen.items():
        questions.setdefault(qid,dict(sub,id=qid))
    output=[]
    for qid,q in questions.items():
        records=[sub for (key,_),sub in chosen.items() if key==qid]
        counts=Counter(record_state(w,s,automatic=automatic) for s in records)
        # A missing record is not invented without an explicit assignment roster.
        absent=0
        if batch.get('roster'):
            recorded={s['student_id'] for s in records}
            absent=len(set(batch['roster'])-recorded)
        errors=counts['incorrect']+(counts['not_submitted'] if automatic else 0)
        valid=counts['correct']+errors
        parent,child,label=hierarchy(q)
        output.append({'id':qid,'label':label,'question':q['question'],'question_type':kind(q),
            'parent':parent,'child':child,'correct':counts['correct'],'errors':errors,
            'valid':valid,'pending':counts['pending'],'not_submitted':counts['not_submitted']+(0 if automatic else absent),
            'unreadable':counts['unreadable'],'ratio':errors/valid if valid else None,
            'submission_ids':[s['id'] for s in records]})
    return sorted(output,key=sort_key)

def batch_summary(w,batch_id,*,automatic=False,rows=None):
    batch=next(b for b in w['batches'] if b['id']==batch_id)
    subs=[s for s in w['submissions'] if s['id'] in batch['submission_ids']]
    # An uploaded blank paper still counts as a submitted student. Explicit
    # not_submitted records describe missing papers; item validity is separate.
    students={s['student_id'] for s in subs if s.get('submission_status')!='not_submitted'}
    scores=batch.get('verified_scores')
    average=None
    if scores and scores.get('source')=='teacher_confirmed' and scores.get('max_score'):
        values=scores.get('values',{})
        if students and set(values)==students and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=scores['max_score'] for v in values.values()):
            average=round(sum(values.values())/len(values),2)
    if rows is None:
        rows=heatmap_rows(w,batch_id,automatic=automatic)
    valid=sum(r['valid'] for r in rows)
    correct=sum(r['correct'] for r in rows)
    execution=p.batch_execution(w,batch_id)
    return {'execution':execution,'correctness':correct/valid if valid else None,'correct_count':correct,'valid_count':valid,
        'submitted_students':len(students),'average':average,'max_score':scores.get('max_score') if scores else None,
        'status':{'ready':'等待批改','partial':'批改部分完成','failed':'批改失败','paused':'批改已暂停','processed':'批改已完成'}[execution['status']]}

def save_scores(w,batch_id,values,max_score):
    if type(max_score) not in (int,float) or not math.isfinite(max_score) or max_score<=0:
        raise ValueError('总分上限无效。')
    if not isinstance(values,dict) or any(not isinstance(k,str) or type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=max_score for k,v in values.items()):
        raise ValueError('分数必须为0至满分之间的有限数值。')
    batch=next(b for b in w['batches'] if b['id']==batch_id)
    allowed={s['student_id'] for s in w['submissions'] if s['id'] in batch['submission_ids']}
    if not set(values).issubset(allowed):raise ValueError('分数包含不属于本次作业的学生。')
    previous=deepcopy(batch.get('verified_scores'))
    batch['verified_scores']={'values':dict(values),'max_score':max_score,'source':'teacher_confirmed','updated_at':c.now()}
    w['events'].append({'id':c.uid(),'command_id':'scores-'+c.uid(),'created_at':c.now(),'previous':previous})

def update_types(w,batch_id,rows):
    batch=next(b for b in w['batches'] if b['id']==batch_id)
    allowed={q['id'] for q in batch['questions']}
    validated=[]
    for row in rows:
        if row.get('id') not in allowed or row.get('question_type') not in TYPES+[UNKNOWN]:
            raise ValueError('题目或题型无效。')
        validated.append({'id':row['id'],'question_type':row['question_type'],
            'question_no':e.text(row.get('question_no',''),80,'题号',True),
            'parent_question_no':e.text(row.get('parent_question_no',''),80,'大题号',True),
            'subquestion_no':e.text(row.get('subquestion_no',''),80,'小问号',True)})
    before=deepcopy(batch['questions'])
    for row in validated:
        q=next(q for q in batch['questions'] if q['id']==row['id'])
        q.update({k:v for k,v in row.items() if k!='id'})
        for sub in w['submissions']:
            if sub['id'] in batch['submission_ids'] and p.item_key(sub)==row['id']:
                sub.update({k:v for k,v in row.items() if k!='id'})
    w['events'].append({'id':c.uid(),'command_id':'question-metadata-'+c.uid(),'created_at':c.now(),'previous':before})

def edit_type(w,entry_id,value):
    if value not in TYPES+[UNKNOWN]:raise ValueError('题型无效。')
    entry=next(n for n in w['notebook'] if n['id']==entry_id)
    before=deepcopy(entry)
    entry['question_type_override']=value
    w['book_events'].append({'id':c.uid(),'entry_id':entry_id,'action':'student_type_edit','created_at':c.now(),'previous':before})

def cause_distribution(rows):
    result={}
    unknown=0
    for n in rows:
        if n.get('deleted') or not n.get('active_error',True):continue
        if n['primary_category']==p.UNKNOWN:unknown+=1;continue
        g=result.setdefault(n['primary_category'],{'confirmed':0,'suggested':0,'ids':[]})
        g['confirmed' if n['category_confirmed'] else 'suggested']+=1
        g['ids'].append(n['id'])
    return result,unknown


def confirm_short(w,submission_id):
    sub=next(s for s in w['submissions'] if s['id']==submission_id)
    q=p.latest(sub,'quick_checks')
    if not q or sub['quick_checks'][-1]['status']!='completed' or q['verdict']=='uncertain' or record_state(w,sub) in ('not_submitted','unreadable'):
        raise ValueError('该记录仍有疑点，须核对原文后复核。')
    a=p.current_deep(sub)
    if a:
        return c.review(w,sub['id'],'confirm',a['analysis']['error_patterns'][0]['label'] if a['analysis']['error_patterns'] else '未发现错误',
            a['analysis']['knowledge_points'],'教师确认当前批改。','short-confirm-'+c.uid(),
            first_error_step=a['analysis']['first_error_step'],is_error=q['verdict']=='incorrect')
    previous=c.latest_review(w,sub['id'])
    if previous and previous['analysis_id']==q['id'] and previous['decision']=='confirm':return previous
    review={'id':c.uid(),'submission_id':sub['id'],'analysis_id':q['id'],'decision':'confirm','label':q['basis'],
        'knowledge_points':q['knowledge_points'],'note':'教师确认短批改结果。','first_error_step':q['first_error_step'],
        'is_error':q['verdict']=='incorrect','created_at':c.now()}
    c.commit(w,'confirm-short-'+review['id'],lambda draft:draft['reviews'].append(review))
    return review


def override_grade(w,submission_id,verdict,note):
    sub=next(s for s in w['submissions'] if s['id']==submission_id)
    if verdict not in ('correct','incorrect') or p.is_blank(sub):
        raise ValueError('请选择正确或错误。卷面留白可在校正作答后重判。')
    note=e.text(note,2000,'备注',True)
    result=p.current_deep(sub) or p.latest(sub,'quick_checks') or {}
    review={'id':c.uid(),'submission_id':submission_id,'analysis_id':result.get('id'),
            'decision':'modify','label':'教师改判','note':note,'knowledge_points':[],
            'first_error_step':None,'is_error':verdict=='incorrect','created_at':c.now(),
            'manual_grade':True,'fingerprint':sub['fingerprint']}
    c.commit(w,'override-'+review['id'],lambda draft:draft['reviews'].append(review))
    return review

def question_error_groups(w,batch_id,submission_ids):
    scope=set(submission_ids);byid={s['id']:s for s in w['submissions'] if s['id'] in scope}
    result=[]
    for group in p.error_groups(w,batch_id):
        ids=[sid for sid in group['submission_ids'] if sid in scope]
        if not ids:continue
        confirmed=sum(p.effective(w,byid[sid])['confirmed'] for sid in ids)
        result.append(dict(group,submission_ids=ids,students=sorted({byid[sid]['student_id'] for sid in ids}),
                           confirmed=confirmed,pending=len(ids)-confirmed))
    return result

CAUSE_COLORS=['#4565ed','#7c83eb','#64b9df','#a68bdb','#e9ac77','#72baaf','#e18ba4','#8ba5d4','#87c8df','#9999ad']

def cause_slices(rows):
    from decimal import Decimal,ROUND_HALF_UP
    groups,unknown=cause_distribution(rows)
    total=sum(len(g['ids']) for g in groups.values())
    slices=[]
    for label,g in sorted(groups.items(),key=lambda pair:(-len(pair[1]['ids']),pair[0])):
        color=CAUSE_COLORS[p.CATEGORIES.index(label)] if label in p.CATEGORIES else '#9999ad'
        slices.append({'label':label,'count':len(g['ids']),'percent':100*len(g['ids'])/total if total else 0,
                       'percent_label':str((Decimal(100)*Decimal(len(g['ids']))/Decimal(total)).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)) if total else '0.0',
                       'confirmed':g['confirmed'],'suggested':g['suggested'],'color':color})
    return slices,total,unknown
