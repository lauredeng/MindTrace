"""Conservative assignment identities, separate from text and OCR revisions."""
from copy import deepcopy
import hashlib
import json
import unicodedata
from uuid import uuid4


def text_signature(value):
    # Normalize typography, never remove signs, decimal points or inequalities.
    value=unicodedata.normalize('NFKC',value.strip().rstrip('。?？'))
    value=value.translate(str.maketrans({'，':',','。':'.','；':';','：':':','？':'?'}))
    return ''.join(value.split()).rstrip('。?？')


def revision(sub):
    fields={k:sub.get(k,'') for k in ('question','question_type','parent_question_no','subquestion_no')}
    return hashlib.sha256(json.dumps(fields,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def attach(batch,submissions):
    """Idempotent additive migration. Existing legacy question IDs stay intact."""
    by_question={q['id']:q for q in batch['questions']}
    groups={}
    used={}
    from core.presentation import shared_question_keys
    verified=shared_question_keys(batch,submissions)
    for sub in submissions:
        if sub['id'] not in batch['submission_ids']:continue
        q=by_question[sub['question_id']]
        key=(sub.get('question_no',''),sub.get('parent_question_no',''),sub.get('subquestion_no',''),
             sub.get('question_type'),verified.get(sub['id']) or text_signature(sub['question']))
        aqid=sub.get('assignment_question_id') or groups.get(key) or q.get('assignment_question_id') or str(uuid4())
        # Never merge two different answers by the same student as OCR variants.
        if (aqid,sub['student_id']) in used and used[aqid,sub['student_id']]!=sub['id']:
            aqid=str(uuid4())
        groups.setdefault(key,aqid)
        used[aqid,sub['student_id']]=sub['id']
        sub.update(assignment_question_id=aqid,question_revision=sub.get('question_revision') or revision(sub))
        q.setdefault('assignment_question_id',aqid)
        q.setdefault('question_revision',sub['question_revision'])
    batch.setdefault('identity_version',1)


def relink(w,batch_id,submission_ids,target_id):
    """Teacher explicitly establishes same-question identity, with an audit trail."""
    from core import classroom as c, product as p
    batch=next(b for b in w['batches'] if b['id']==batch_id)
    records=[s for s in w['submissions'] if s['id'] in batch['submission_ids']]
    attach(batch,records)
    if not submission_ids or not set(submission_ids)<=set(batch['submission_ids']):
        raise ValueError('请选择本次作业中的有效作答。')
    targets=[s for s in records if s['assignment_question_id']==target_id]
    if not targets:raise ValueError('目标题目不存在。')
    members=[s for s in records if s['id'] in submission_ids or s['assignment_question_id']==target_id]
    if len({s['student_id'] for s in members})!=len(members):
        raise ValueError('合并后同一学生会出现两份作答，请先核对。')
    def apply(draft):
        for sub in draft['submissions']:
            if sub['id'] not in submission_ids:continue
            previous=sub['assignment_question_id']
            sub['assignment_question_id']=target_id
            # Reference identity changes require explicit re-confirmation.
            sub.pop('reference_revision',None)
            sub['identity_history']=sub.get('identity_history',[])+[
                {'id':c.uid(),'previous':previous,'target':target_id,'created_at':c.now()}]
            sub['fingerprint']=p.digest([sub['fingerprint'],target_id,c.uid()])
            p.sync_notebook(draft,sub['id'])
    c.commit(w,'relink-'+c.uid(),apply)


def roster_snapshot(w,rows):
    # Keep exact student numbers and leading zeroes; do not silently infer identity.
    return list(dict.fromkeys(w.get('student_roster') or [row['student_id'] for row in rows]))


def assignment_counts(w,batch):
    records=[s for s in w['submissions'] if s['id'] in batch['submission_ids']]
    received={s['student_id'] for s in records}
    expected=set(batch.get('roster',[]))
    return {'expected':len(expected),'received':len(received),'missing':sorted(expected-received),
            'unexpected':sorted(received-expected) if expected else []}
