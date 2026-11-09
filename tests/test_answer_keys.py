import json

import pytest

from core import ai, answer_keys, classroom as c, product as p
from core.limits import Limits, UsageLimitError, UsageLimiter, auto_resume


def create(rows):
    w=c.new_workspace()
    batch=p.create_batch(w,'同一份练习',rows,'manual',grading_policy=p.CLASSROOM_POLICY)
    return w,batch


def choice(student,answer,number='1'):
    return {'student_id':student,'question':f'第{number}题，选择正确命题。A. 1=1 B. 1=0 C. 2=2 D. 2=0',
            'question_type':'选择题','question_no':number,'answer':answer}


def forbidden(*args,**kwargs):
    raise AssertionError('Unexpected provider call')


def test_one_draft_then_local_multi_choice_and_selective_revision(tmp_path):
    w,b=create([choice('A','CA'),choice('B','A'),choice('C','ABC'),choice('D',''),
                choice('A','AC','2')])
    batch_id=b['id']
    first,second=p.reference_catalog(w,b)[0]
    calls=[]
    def model(system,data,**kwargs):
        payload=json.loads(data)
        assert set(payload)=={'question','question_type'}
        assert kwargs['purpose']=='reference_answer'
        calls.append(payload['question'])
        return {'answer':'AC','rubric':'按选项集合比对','needs_review':False}
    assert p.generate_references(w,batch_id,model)==''
    assert p.generate_references(w,batch_id,forbidden)==''
    assert len(calls)==2
    assert not any(sub.get('reference_revision') for sub in w['submissions'])
    snapshot=p.digest(b['answer_keys'])
    assert p.save_references(w,batch_id,{first:('AC','按选项集合比对'),second:('AC','')},snapshot)==2
    assert p.run_batch(w,batch_id,forbidden)['complete']==5
    assert [p.effective(w,s)['verdict'] for s in w['submissions']]==[
        'correct','incorrect','incorrect','incorrect','correct']
    prior=[p.latest(s,'quick_checks')['id'] for s in w['submissions']]
    batch=w['batches'][0]
    assert batch['answer_keys'][first]['confirmed']['source']=='ai_confirmed'
    assert batch['answer_keys'][second]['confirmed']['source']=='teacher'
    assert len(w['notebook'])==2 and all(row['correct_answer']=='AC' for row in w['notebook'])
    with pytest.raises(ValueError,match='另一窗口'):
        p.save_references(w,batch_id,{first:('A','')},snapshot)
    p.save_references(w,batch_id,{first:('A','')},p.digest(batch['answer_keys']))
    assert [p.effective(w,s)['verdict'] for s in w['submissions']]==[
        'uncertain','uncertain','uncertain','incorrect','correct']
    assert p.run_batch(w,batch_id,forbidden)['complete']==5
    assert [p.effective(w,s)['verdict'] for s in w['submissions']]==[
        'incorrect','correct','incorrect','incorrect','correct']
    assert p.latest(w['submissions'][-1],'quick_checks')['id']==prior[-1]
    assert w['submissions'][0]['quick_checks'][0]['id']==prior[0]
    file=tmp_path/'class.json'
    c.save(w,file)
    assert c.load(file)['batches'][0]['answer_keys'][first]['history'][0]['answer']=='AC'


def test_safe_answer_comparison_and_review_required_for_partial_key():
    assert answer_keys.compare('选择题','ｃ、Ａ','AC') is True
    assert answer_keys.compare('选择题','A','AC') is False
    assert answer_keys.compare('选择题','ABC','AC') is False
    assert answer_keys.compare('选择题','ABC 或 AB','AC') is None
    assert answer_keys.compare('填空题','2/4','0.5') is True
    assert answer_keys.compare('填空题','2','3') is False
    assert answer_keys.compare('填空题','2','3',has_rubric=True) is None
    assert answer_keys.compare('填空题','0.33','1/3',approximate=True) is None
    assert answer_keys.compare('填空题','[0,1)','[0,1]') is None
    w,b=create([choice('A','AC')])
    p.generate_references(w,b['id'],lambda *_args,**_kwargs:{'needs_review':True})
    assert p.batch_execution(w,b['id'])['status']=='ready'
    entry=next(iter(b['answer_keys'].values()))
    assert not entry.get('draft') and '题目' in entry['error']


def test_limiter_waits_automatically_but_daily_limit_stops():
    now=[1000.0]
    limiter=UsageLimiter(lambda:now[0])
    limits=Limits(session_minute=1,session_day=2)
    admitted=[]
    countdown=[]
    def model(data):
        with limiter.request('fixture',1,limits):
            admitted.append(data)
    def advance(seconds):
        now[0]+=seconds
    resumed=auto_resume(model,lambda reason,seconds:countdown.append((reason,seconds)),sleep=advance)
    resumed('first')
    resumed('second')
    with pytest.raises(UsageLimitError) as failure:
        resumed('third')
    assert failure.value.reason=='daily'
    assert admitted==['first','second']
    assert countdown[0]==('minute',60) and countdown[-1]==('minute',0)


def test_provider_429_retry_is_bounded():
    calls=[]
    def model():
        calls.append(1)
        raise UsageLimitError('429',retry_after=1,reason='provider')
    wrapped=auto_resume(model,lambda *_:None,sleep=lambda *_:None)
    with pytest.raises(UsageLimitError):
        wrapped()
    assert len(calls)==3


def test_truncated_grading_resume_skips_original_paid_request():
    w,b=create([choice('A','AC')])
    budgets=[]
    def model(system, data, *, max_tokens, **kwargs):
        budgets.append(max_tokens)
        if len(budgets)==1:raise ai.OutputTruncatedError('length')
        if len(budgets)==2:raise UsageLimitError('daily',reason='daily')
        return {'verdict':'correct','final_answer_status':'correct','basis':'两项都正确。',
                'evidence_id':'ANSWER','process_checked':False,'first_error_step':None}
    assert p.run_batch(w,b['id'],model)['paused']
    assert p.run_batch(w,b['id'],model)['complete']==1
    assert budgets==[2800,5200,5200]
