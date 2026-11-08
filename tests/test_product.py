"""V1.2 offline contract tests. Never evidence of model mathematics accuracy."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import json
import pytest
from core import product as p,education as e,classroom as c
from core.limits import UsageLimitError
from test_education import CASES,report

def quick(sub,verdict='incorrect',cause='公式或定理遗忘'):
    return {'verdict':verdict,'basis':'局部离线依据','evidence_quote':(sub['steps'] or [sub['answer'] or sub['question']])[0],
        'first_error_step':2 if verdict=='incorrect' and len(sub['steps'])>1 else None,
        'knowledge_points':['等价变形'],'category':cause,'category_basis':'本题的候选原因，仍需确认','process_checked':True}

def correction(cause='公式或定理遗忘'):
    return {'answer':'x=2','steps':[{'text':'2*x+6=10','reason':'分配律'},{'text':'2*x=4','reason':'等式性质'},{'text':'x=2','reason':'两边除以2'}],
        'knowledge_points':['等价变形'],'category':cause,'category_basis':'本题候选原因',
        'supplements':[{'kind':'formula','content':'a(b+c)=ab+ac','conditions':'实数乘法满足分配律','connection':'本题展开括号时需要对两项都乘2'}],
        'uncertainties':['离线测试材料，不是模型实测']}

def deep(sub,cause='公式或定理遗忘'):
    return dict(report(sub,2),correction=correction(cause))

def workspace():
    w=c.new_workspace()
    b=p.create_batch(w,'测试批次',[CASES[10]],'constructed_examples')
    return w,b,w['submissions'][0]


def test_classroom_grades_answers_and_blank_without_review_or_deep_calls():
    from core import presentation as v
    w=c.new_workspace()
    rows=[dict(student_id=s,question='圆的半径是多少？',question_type='填空题',answer=answer)
          for s,answer in [('A','2'),('B','3'),('C',''),('D','[无法辨认]')]]
    batch=p.create_batch(w,'班级批改',rows,grading_policy=p.CLASSROOM_POLICY)
    attempts=[]
    def model(prompt,user,**kwargs):
        answer=json.loads(user)['answer']
        attempts.append((answer,kwargs['purpose']))
        return dict(verdict='correct' if answer=='2' else 'incorrect',
                    evidence_id='S99',first_error_step='S99',process_checked=False,basis='核对最终答案。')
    p.run_batch(w,batch['id'],model)
    assert attempts==[('2','quick_grading'),('3','quick_grading')]
    row,=v.heatmap_rows(w,batch['id'],automatic=True)
    assert (row['correct'],row['errors'],row['not_submitted'],row['unreadable'])==(1,2,1,1)
    summary=v.batch_summary(w,batch['id'],automatic=True)
    assert summary['valid_count']==3 and summary['correctness']==pytest.approx(1/3)
    assert not w['reviews']


def test_classroom_unresolved_proof_uses_short_process_check():
    w=c.new_workspace()
    batch=p.create_batch(w,'证明题',[dict(student_id='A',question='证明两个角相等。',question_type='解答题',
        steps=['根据对顶角相等，可知两个角相等。'],answer='相等')],grading_policy=p.CLASSROOM_POLICY)
    sub=w['submissions'][0]
    def model(prompt,user,**kwargs):
        if kwargs['purpose']=='quick_grading':
            assert not json.loads(user)['answer_only']
            return dict(verdict='correct',evidence_id='S99',process_checked=True,basis='引用无效。')
        return report(sub,overall='appears_correct')
    p.run_batch(w,batch['id'],model)
    assert sub['quick_checks'][0]['verdict']=='uncertain'
    assert sub['analyses'][0]['teacher_only'] and 'correction' not in sub['analyses'][0]
    assert p.effective(w,sub)['verdict']=='correct'


@pytest.mark.parametrize('kind,reason,expected',[
    ('填空题','missing_process','correct'),
    ('填空题','other','uncertain'),
    ('解答题','missing_process','uncertain'),
    ('未分类','missing_process','uncertain'),
])
def test_answer_only_question_requires_no_work_but_other_doubts_remain(kind,reason,expected):
    sub=e.normalize_submission(dict(student_id='A',question='双曲线离心率是多少？',question_type=kind,answer='3/2'))
    def model(prompt,user,**options):
        assert json.loads(user)['question_type']==kind
        return dict(verdict='uncertain',final_answer_status='correct',evidence_id='ANSWER',
                    process_checked=False,uncertainty_reason=reason,basis='答案为 3/2。')
    result=p.quick_check(sub,model)
    assert result['verdict']==expected
    assert result['evidence_quote']=='3/2'


def test_only_truncated_question_retries_and_quota_resume_reuses_other_success():
    from core.ai import OutputTruncatedError
    w=c.new_workspace()
    rows=[dict(student_id='A',question=q,question_type='填空题',answer='1') for q in ('第一题','第二题')]
    batch=p.create_batch(w,'截断恢复',rows)
    attempts=[]
    def model(prompt,user,**options):
        question=json.loads(user)['question']
        attempts.append(question)
        if question=='第二题' and attempts.count(question)==1:
            raise OutputTruncatedError('达到长度上限')
        if question=='第二题' and attempts.count(question)==2:
            raise UsageLimitError('暂时限流')
        return dict(verdict='correct',final_answer_status='correct',evidence_id='ANSWER',
                    process_checked=False,basis='答案正确')
    assert p.run_batch(w,batch['id'],model)['status']=='paused'
    assert attempts==['第一题','第二题','第二题']
    assert p.run_batch(w,batch['id'],model)['status']=='processed'
    assert attempts==['第一题','第二题','第二题','第二题']


def test_deep_truncation_stops_after_one_retry_and_keeps_short_result():
    from core.ai import OutputTruncatedError
    w,b,sub=workspace()
    attempts=[]
    def model(prompt,user,**options):
        attempts.append(options['purpose'])
        if options['purpose']=='error_analysis':
            raise OutputTruncatedError('达到长度上限')
        return quick(sub)
    result=p.run_batch(w,b['id'],model)
    assert attempts==['quick_grading','error_analysis','error_analysis']
    assert result['status']=='partial'
    assert p.latest(sub,'quick_checks')['verdict']=='incorrect'
    assert sub['analyses'][-1]['error_type']=='OutputTruncatedError'

def fake_call(sub,calls,correct=False):
    def call(system,user,**kw):
        calls.append(kw['purpose'])
        return quick(sub,'correct' if correct else 'incorrect') if kw['purpose']=='quick_grading' else deep(sub)
    return call

def test_batch_two_layers_skip_correct_and_auto_collect_wrong():
    w,b,s=workspace();calls=[]
    p.run_batch(w,b['id'],fake_call(s,calls))
    assert calls==['quick_grading','error_analysis']
    assert len(w['notebook'])==1 and w['notebook'][0]['correct_answer']=='x=2'
    assert w['notebook'][0]['supplements'][0]['conditions']
    assert not w['notebook'][0]['category_confirmed']
    p.run_batch(w,b['id'],fake_call(s,calls))
    assert len(calls)==2 and len(w['notebook'])==1
    w2=c.new_workspace();b2=p.create_batch(w2,'正确题',[CASES[2]]);s2=w2['submissions'][0];calls2=[]
    p.run_batch(w2,b2['id'],fake_call(s2,calls2,True))
    assert calls2==['quick_grading'] and not w2['submissions'][0]['analyses'] and not w2['notebook']

def test_quota_pauses_then_resume_reuses_success():
    w,b,s=workspace();calls=[]
    def limited(system,user,**kw):
        calls.append(kw['purpose'])
        if kw['purpose']=='error_analysis':raise UsageLimitError('额度不足')
        return quick(s)
    assert p.run_batch(w,b['id'],limited)['paused']
    assert b['status']=='paused'
    p.run_batch(w,b['id'],fake_call(s,calls))
    assert calls.count('quick_grading')==1 and calls.count('error_analysis')==2

@pytest.mark.parametrize('field,value',[('evidence_quote','捏造原文'),('first_error_step',99),('category','心理障碍'),('process_checked','yes')])
def test_malformed_quick_not_published(field,value):
    _,_,s=workspace();payload=quick(s);payload[field]=value
    r=p.quick_check(s,lambda *a,**kw:payload)
    assert r['status']=='failed'
    assert p.effective(c.new_workspace(),s)['verdict']=='uncertain'

def test_missing_process_cannot_claim_correct():
    _,_,s=workspace();payload=quick(s,'correct');payload['process_checked']=False
    assert p.quick_check(s,lambda *a,**kw:payload)['verdict']=='uncertain'
    payload=quick(s,'correct');payload['first_error_step']=1
    assert p.quick_check(s,lambda *a,**kw:payload,True)['status']=='failed'

def test_shared_question_headcounts_and_distinct_same_number():
    w=c.new_workspace()
    a=deepcopy(CASES[10]);b=dict(a,student_id='OTHER');d=dict(a,question='x+1=2',question_no=a['question_no'],student_id='THIRD')
    batch=p.create_batch(w,'同题',[a,b,d])
    assert len(batch['questions'])==2
    for s in w['submissions']:
        p.quick_check(s,lambda *a,_s=s,**kw:quick(_s))
    stats=p.per_question(w,batch['id'])
    assert sorted(g['total'] for g in stats)==[1,2]
    assert sum(g['confirmed_incorrect'] for g in stats)==0
    assert p.create_batch(w,'同题',[a,b,d])['id']==batch['id']
    with pytest.raises(ValueError,match='多份作答'):
        p.create_batch(w,'重复',[a,a])

def test_repeated_batches_do_not_inflate_global_pupil_count():
    w,b,s=workspace()
    p.create_batch(w,'另一次',[CASES[10]])
    assert p.per_question(w)[0]['total']==1
    assert len(w['submissions'])==2

def test_teacher_override_resolves_book_and_stats_with_history():
    w,b,s=workspace();p.run_batch(w,b['id'],fake_call(s,[]))
    c.review(w,s['id'],'modify','原解法有效',[],'先前误判','override',is_error=False)
    p.sync_notebook(w,s['id'])
    g=p.per_question(w,b['id'])[0]
    assert g['correct']==g['confirmed_correct']==1 and g['incorrect']==0
    assert not w['notebook'][0]['active_error']
    assert p.cause_stats(w['notebook'])['confirmed']=={}
    assert w['reviews'] and w['book_events'][-1]['action']=='source_corrected'

def test_rejected_and_unknown_not_counted_as_confirmed():
    w,b,s=workspace();p.run_batch(w,b['id'],fake_call(s,[]))
    c.review(w,s['id'],'reject','判断不成立',[],'仍需核对','reject')
    assert p.per_question(w,b['id'])[0]['uncertain']==1
    assert p.per_question(w,b['id'])[0]['confirmed_incorrect']==0

def test_reclassification_preserves_ai_and_source_and_delete_tombstone():
    w,b,s=workspace();p.run_batch(w,b['id'],fake_call(s,[]))
    n=w['notebook'][0];original=s['question']
    p.edit_entry(w,n['id'],'解题方法选择不当',['推理或关键步骤遗漏'],'我的解释',True,'个人修订题目')
    assert n['ai_category']=='公式或定理遗忘'
    assert s['question']==original
    p.sync_notebook(w,s['id'],manual=True)
    assert n['primary_category']=='解题方法选择不当' and n['notes']=='我的解释'
    stats=p.cause_stats(p.notebook_rows(w,s['student_id']))
    assert stats['confirmed']=={'解题方法选择不当':1}
    assert p.notebook_rows(w,s['student_id'],query='个人修订',cause='解题方法选择不当')
    p.delete_entry(w,n['id']);p.sync_notebook(w,s['id'],manual=True)
    assert not p.notebook_rows(w,s['student_id'])
    p.delete_entry(w,n['id'],False)
    assert len(p.notebook_rows(w,s['student_id']))==1
    assert any(v['action']=='student_edit' and v['previous']['primary_category']=='公式或定理遗忘' for v in w['book_events'])

def test_category_uncertainty_excluded_even_when_checkbox_confirmed():
    w,b,s=workspace();p.run_batch(w,b['id'],fake_call(s,[]));n=w['notebook'][0]
    p.edit_entry(w,n['id'],p.UNKNOWN,[],'',True)
    assert not n['category_confirmed'] and p.cause_stats([n])['pending']==1
    assert not p.notebook_rows(w,'ANOTHER')
    with pytest.raises(ValueError):p.edit_entry(w,n['id'],'计算失误',['计算失误'],'',True)

def test_unanswered_question_can_solve_collect_and_freely_ask():
    row=dict(CASES[10],steps=[],answer='')
    with pytest.raises(ValueError):e.normalize_submission(row)
    s=e.normalize_submission(row,'self_study',allow_unanswered=True)
    w=c.new_workspace();w['submissions'].append(s)
    payload={'known_conditions':['方程给定'],'goal':'求x','method':'等价变形','correction':correction('暂无解题思路')}
    calls=[]
    def call(*a,**kw):calls.append(kw['purpose']);return payload
    sol=p.solve_question(s,'full',call)
    assert sol['status']=='completed'
    assert p.solve_question(s,'full',call)['id']==sol['id'] and len(calls)==1
    n=p.sync_notebook(w,s['id'],True,'暂无解题思路')
    assert len(w['notebook'])==1 and n['correct_answer']=='x=2'
    for i in range(4):
        p.study_turn(w,s,'ask_student','',lambda *a,**kw:{'message':'解释两边同除的条件','purpose':'检查等价变形依据','next_suggestion':'可直接查看完整解答'})
    assert len(w['study_sessions'][0]['turns'])==4
    p.study_turn(w,s,'reply','为什么要两边同时除？',lambda *a,**kw:{'message':'保持等式关系','purpose':'回答学生的新问题','next_suggestion':''})
    assert w['study_sessions'][0]['turns'][-1]['reply']=='为什么要两边同时除？'
    assert not w['tasks'] and not w['attempts']

def test_old_json_roundtrip_retains_data_and_adds_optional_lists(tmp_path):
    w,b,s=workspace();legacy=deepcopy(w)
    for key in ('batches','notebook','book_events','study_sessions'):legacy.pop(key)
    clean=c.validate_workspace(legacy)
    assert clean['submissions']==legacy['submissions']
    assert clean['notebook']==[]
    path=tmp_path/'workspace.json';c.save(clean,path)
    loaded=c.load(path)
    assert loaded['submissions']==legacy['submissions']
    p.sync_notebook(loaded,s['id'],True,'暂无解题思路')
    c.save(loaded,path)
    assert c.load(path)['notebook'][0]['primary_category']=='暂无解题思路'

def test_stale_deep_labels_not_used_after_new_correct_quick():
    w,b,s=workspace();p.run_batch(w,b['id'],fake_call(s,[]))
    assert p.error_groups(w)
    payload=quick(s,'correct')
    # Match local final-answer tool to avoid a deliberate tool conflict in this test.
    s['task_type']='general';s['question']='解释这个数学方法';s['steps']=['原始文本'];s['answer']='说明'
    payload['evidence_quote']='原始文本'
    p.quick_check(s,lambda *a,**kw:payload,True)
    assert not p.error_groups(w)

def test_shared_stem_ocr_references_are_reconstituted():
    from PIL import Image
    import io
    stream=io.BytesIO();Image.new('RGB',(100,100),'white').save(stream,format='PNG')
    payload={'transcription':'匿名题号Q','warnings':[],'records':[{'student_id':'A','question_no':'Q','question':'',
        'question_ref':'SHARED','steps':[],'answer':'','topic':e.TOPICS[0],'uncertainties':[]}]}
    r=e.extract_image(stream.getvalue(),lambda *a,**kw:payload,known_questions=[{'id':'SHARED','question':'求集合的并集'}])
    assert r['records'][0]['question']=='求集合的并集'


def test_source_id_anchor_keeps_original_and_model_wording_separate():
    _,_,s=workspace();payload=quick(s)
    payload['evidence_id']='S1';payload['evidence_quote']='模型格式化过的版本'
    rec=p.quick_check(s,lambda *a,**kw:payload)
    assert rec['status']=='completed' and rec['evidence_quote']==s['steps'][0]
    assert rec['model_evidence_quote']=='模型格式化过的版本'
    payload['evidence_id']=[]
    assert p.quick_check(s,lambda *a,**kw:payload,True)['status']=='failed'


def test_same_question_identical_wrong_line_merges_model_wording():
    w=c.new_workspace();a=dict(CASES[10],student_id='A');b=dict(CASES[10],student_id='B')
    batch=p.create_batch(w,'两份相同错误',[a,b])
    for i,s in enumerate(w['submissions']):
        p.quick_check(s,lambda *a,_s=s,**kw:quick(_s))
        payload=deep(s);payload['error_patterns'][0]['label']='模型措辞'+str(i)
        p.deep_analyze(s,lambda *a,_p=payload,**kw:_p)
    groups=p.error_groups(w,batch['id'])
    assert len(groups)==1 and len(groups[0]['students'])==2
    assert len(groups[0]['original_labels'])==2
    assert list(p.per_question(w,batch['id'])[0]['patterns'].values())==[2]

def test_self_study_never_enters_class_question_counts():
    w,b,s=workspace()
    self_row=e.normalize_submission(dict(CASES[10],student_id='SELF',steps=[],answer=''),'self_study',allow_unanswered=True)
    w['submissions'].append(self_row)
    assert p.per_question(w)[0]['total']==1


def test_known_wrong_reference_not_published():
    _,_,s=workspace();bad=correction();bad['answer']='x=999'
    with pytest.raises(ValueError,match='参考解未发布'):
        p.validate_correction(bad,s)


def test_hint_does_not_erase_previous_full_reference():
    _,_,s=workspace()
    payload={'known_conditions':['原方程'],'goal':'求x','method':'等价变形','correction':correction()}
    p.solve_question(s,'full',lambda *a,**kw:payload)
    p.solve_question(s,'hint',lambda *a,**kw:payload)
    assert p.correction_for(s)['answer']=='x=2'


def test_all_batch_requests_fail_never_claims_processed_and_can_retry():
    w,b,s=workspace()
    def fail(*a,**kw):raise RuntimeError('离线模拟服务故障')
    result=p.run_batch(w,b['id'],fail)
    assert b['status']==result['status']=='failed'
    assert result['complete']==0 and result['failed']==1
    assert not s['analyses']  # Never deepen using an absent quick result.
    calls=[]
    recovered=p.run_batch(w,b['id'],fake_call(s,calls))
    assert recovered['status']==b['status']=='processed'
    assert recovered['complete']==1 and calls==['quick_grading','error_analysis']
    assert len(s['quick_checks'])==2 and len(s['analyses'])==1


def test_partial_batch_retry_only_failed_quick_and_missing_deep():
    w=c.new_workspace()
    b=p.create_batch(w,'部分失败',[dict(CASES[10],student_id=sid) for sid in ('A','B','C')])
    subs=w['submissions'];attempts=[]
    def first(system,user,**kw):
        stage=kw['purpose'];attempts.append(stage)
        if stage=='quick_grading':
            index=attempts.count(stage)-1
            if index==1:raise RuntimeError('第二份短批改失败')
            return quick(subs[index])
        return deep(subs[0])
    result=p.run_batch(w,b['id'],first)
    assert result['status']=='partial' and result['complete']==2 and result['failed']==1
    counts=[(len(s['quick_checks']),len(s['analyses'])) for s in subs]
    resumed=[]
    p.run_batch(w,b['id'],fake_call(subs[1],resumed))
    assert resumed==['quick_grading','error_analysis']
    assert b['status']=='processed'
    assert [(len(s['quick_checks']),len(s['analyses'])) for s in subs]==[counts[0],(2,1),counts[2]]
    assert len(w['notebook'])==3


def test_deep_failure_is_partial_and_retry_reuses_quick():
    w,b,s=workspace();calls=[]
    def fail_deep(*a,**kw):
        calls.append(kw['purpose'])
        if kw['purpose']=='error_analysis':raise ValueError('深析响应不完整')
        return quick(s)
    result=p.run_batch(w,b['id'],fail_deep)
    assert result['status']=='partial' and result['quick_completed']==1 and result['complete']==0
    p.run_batch(w,b['id'],fake_call(s,calls))
    assert b['status']=='processed' and calls.count('quick_grading')==1
    assert calls.count('error_analysis')==2


def test_quick_rate_limit_stops_immediately_and_resumes_without_success_replay():
    w=c.new_workspace();b=p.create_batch(w,'限流续跑',[dict(CASES[10],student_id=sid) for sid in ('A','B')])
    subs=w['submissions'];calls=[]
    def limit_second(*a,**kw):
        calls.append(kw['purpose'])
        if len(calls)==2:raise UsageLimitError('操作较频繁，请稍候再试')
        return quick(subs[0])
    result=p.run_batch(w,b['id'],limit_second)
    assert result['status']=='paused' and calls==['quick_grading','quick_grading']
    assert result['blocked']==1 and result['failed']==0
    assert '稍候' in b['pause_reason']
    resumed=[]
    p.run_batch(w,b['id'],fake_call(subs[1],resumed))
    assert resumed==['quick_grading','error_analysis','error_analysis']
    assert b['status']=='processed' and 'pause_reason' not in b
    assert len(subs[0]['quick_checks'])==1


def test_force_failure_cannot_silently_reuse_old_success_on_retry():
    w,b,s=workspace();p.run_batch(w,b['id'],fake_call(s,[]))
    def fail(*a,**kw):raise RuntimeError('强制重跑失败')
    assert p.run_batch(w,b['id'],fail,force=True)['status']=='failed'
    calls=[];p.run_batch(w,b['id'],fake_call(s,calls))
    assert calls==['quick_grading','error_analysis'] and b['status']=='processed'


def test_deep_force_failure_keeps_history_but_requires_real_retry():
    w,b,s=workspace();p.run_batch(w,b['id'],fake_call(s,[]))
    old=p.current_deep(s)
    def fail(*a,**kw):raise RuntimeError('重新深析失败')
    p.deep_analyze(s,fail,force=True)
    assert p.batch_execution(w,b['id'])['status']=='partial'
    assert old in s['analyses']
    calls=[];p.run_batch(w,b['id'],fake_call(s,calls))
    assert calls==['error_analysis'] and b['status']=='processed'


def test_resume_after_json_reload_and_legacy_false_completed_label(tmp_path):
    w,b,s=workspace()
    def fail(*a,**kw):raise RuntimeError('离线故障')
    p.run_batch(w,b['id'],fail);b['status']='processed'  # Old bug's saved status.
    path=tmp_path/'batch.json';c.save(w,path);loaded=c.load(path)
    from core import presentation as v
    assert v.batch_summary(loaded,b['id'])['status']=='批改失败'
    sub=loaded['submissions'][0];calls=[]
    assert p.run_batch(loaded,b['id'],fake_call(sub,calls))['status']=='processed'
    assert len(sub['quick_checks'])==2


def test_real_minute_limiter_resume_after_cooldown_and_json_reload(tmp_path):
    from core.limits import UsageLimiter,Limits
    w,b,s=workspace();clock=[1000.0];limiter=UsageLimiter(clock=lambda:clock[0]);calls=[]
    def admitted(system,user,**kw):
        with limiter.request('batch-recovery',1,Limits(session_minute=1)):
            calls.append(kw['purpose'])
            return quick(s) if kw['purpose']=='quick_grading' else deep(s)
    assert p.run_batch(w,b['id'],admitted)['status']=='paused'
    assert calls==['quick_grading']
    path=tmp_path/'paused.json';c.save(w,path);restored=c.load(path)
    clock[0]+=61  # Actual rolling-minute admission recovery, no wall-clock sleep.
    assert p.run_batch(restored,b['id'],admitted)['status']=='processed'
    assert calls==['quick_grading','error_analysis']
    assert len(restored['submissions'][0]['quick_checks'])==1


def test_reopening_old_and_new_sources_does_not_rewrite_notebook_or_undo_latest_source():
    w,b,s=workspace();p.run_batch(w,b['id'],fake_call(s,[]))
    newer=p.create_batch(w,'第二次作业',[CASES[10]]);sub=w['submissions'][-1]
    p.run_batch(w,newer['id'],fake_call(sub,[]))
    entry=w['notebook'][0];p.edit_entry(w,entry['id'],'计算失误',[],'本人备注')
    before=deepcopy(w['book_events'])
    for _ in range(3):
        for source in w['submissions']:p.sync_notebook(w,source['id'])
    assert w['book_events']==before
    assert entry['submission_id']==sub['id'] and entry['batch_id']==newer['id']
    assert entry['notes']=='本人备注' and set(entry['source_ids'])=={s['id'],sub['id']}


def test_confirmed_correct_later_submission_stays_resolved_when_reopening_old_wrong_work():
    from core import presentation as v
    w,b,old=workspace();p.run_batch(w,b['id'],fake_call(old,[]))
    row=dict(CASES[10],steps=['2*(x+3)=10','x+3=5','x=2'],answer='x=2')
    newer=p.create_batch(w,'正确的再次作答',[row]);sub=w['submissions'][-1]
    p.run_batch(w,newer['id'],fake_call(sub,[],True));v.confirm_short(w,sub['id']);p.sync_notebook(w,sub['id'])
    entry=w['notebook'][0];assert not entry['active_error']
    before=deepcopy(w['book_events'])
    for _ in range(3):
        for source in w['submissions']:p.sync_notebook(w,source['id'])
    assert not entry['active_error'] and entry['resolved_by']==sub['id']
    assert w['book_events']==before and entry['submission_id']==old['id']
