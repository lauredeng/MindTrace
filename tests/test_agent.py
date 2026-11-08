"""Controller contracts with explicit offline model decisions, not accuracy evidence."""
from copy import deepcopy
import json
import pytest
from core import agent as a,classroom as c,education as e,product as p,collaboration as x
from core.limits import UsageLimitError
from test_education import CASES,exercise,grade


def workspace():
 w=c.new_workspace();s=e.normalize_submission(dict(CASES[10],student_id='A'));w['submissions'].append(s)
 return w,s

def decision(action='ask_student',message='括号中的常数项也要乘2吗？',**kw):
 return dict({'action':action,'goal':'确认分配律的作用范围','rationale':'原始第二步漏乘，需要区分规则理解与漏写',
              'evidence_ids':['S2'],'message':message,'step':2,'target':'original','verification_claim':'unverified'},**kw)

def test_different_student_evidence_selects_different_actions():
 for reply,expected in [('我认为只有x需要乘2','ask_student'),('我知道两项都乘2，只是写漏了','explain_step')]:
  w,s=workspace()
  def model(system,user,**kw):
   assert kw['purpose']=='agent_decision'
   return decision('ask_student' if '只有x' in json.loads(user)['sources']['REPLY'] else 'explain_step',evidence_ids=['S2','REPLY'])
  result=a.run(w,s['id'],'A',model,reply=reply)
  assert result['trace'][0]['action']==expected
  assert result['status']==('waiting_student' if expected=='ask_student' else 'delivered')
  assert len(w['study_sessions'][0]['turns'])==1


def test_model_selects_tool_and_uses_actual_observation_before_explaining():
 w,s=workspace();before=deepcopy(s);calls=[]
 def model(system,user,**kw):
  data=json.loads(user);calls.append(data)
  if not data['observations']:return decision('verify_math','')
  key=next(iter(data['observations']));observed=data['observations'][key]
  assert any(row.get('step')==2 and row['verdict']=='incorrect' for row in observed['checks'])
  return decision('explain_step','工具显示第二步相邻变形不成立；需要对括号中两项都乘2。',evidence_ids=['S2',key],verification_claim='local_checked')
 result=a.run(w,s['id'],'A',model)
 assert result['model_calls']==2 and result['tool_calls']==1 and result['status']=='delivered'
 assert s==before and not w['reviews'] and not w['notebook']


@pytest.mark.parametrize('bad',[{'action':'execute_python'},{'action':[]},{'evidence_ids':['OTHER_STUDENT']},{'step':99},{'step':True},{'target':'filesystem'},{'verification_claim':'local_checked'},{'code':'delete records'}])
def test_invalid_or_unauthorized_decisions_never_execute(bad,monkeypatch):
 w,s=workspace();before=deepcopy(s)
 monkeypatch.setattr(a.math_tools,'evidence',lambda *_:pytest.fail('Unauthorized tool execution'))
 result=a.run(w,s['id'],'A',lambda *args,**kw:decision(**bad))
 assert result['status']=='stopped' and result['model_calls']==3 and result['tool_calls']==0
 assert all(t['policy']=='rejected' for t in result['trace'])
 assert before==s


def test_direct_preference_blocks_questions_and_replans_to_explanation():
 w,s=workspace();calls=[]
 def model(*args,**kw):
  calls.append(1);return decision() if len(calls)==1 else decision('explain_step','直接说明：括号内每项都乘2。')
 result=a.run(w,s['id'],'A',model,reply='请直接解释',preference='direct')
 assert result['trace'][0]['policy']=='rejected' and result['status']=='delivered'
 assert not any(t.get('agent_action')=='ask_student' for t in w['study_sessions'][0]['turns'])


def test_waiting_is_durable_and_repeated_begin_does_not_call_model(tmp_path):
 w,s=workspace();calls=[]
 def model(*args,**kw):calls.append(1);return decision()
 first=a.run(w,s['id'],'A',model,command_id='once')
 assert a.run(w,s['id'],'A',model,command_id='once')['id']==first['id']
 assert a.run(w,s['id'],'A',model)['id']==first['id']
 path=tmp_path/'w.json';c.save(w,path);loaded=c.load(path)
 assert a.latest_run(loaded,s['id'],'A')['status']=='waiting_student' and len(calls)==1


def test_repeated_question_is_rejected_and_new_strategy_is_used():
 w,s=workspace();a.run(w,s['id'],'A',lambda *args,**kw:decision())
 calls=[]
 def model(*args,**kw):
  calls.append(1);return decision() if len(calls)==1 else decision('explain_step','换成面积分配的解释，逐项对应两个乘积。')
 result=a.run(w,s['id'],'A',model,reply='仍然不明白')
 assert result['trace'][0]['policy']=='rejected' and result['status']=='delivered'


def test_same_tool_is_not_reexecuted_and_loop_is_bounded(monkeypatch):
 w,s=workspace();real=a.math_tools.evidence;calls=[]
 def tool(material):calls.append(1);return real(material)
 monkeypatch.setattr(a.math_tools,'evidence',tool)
 result=a.run(w,s['id'],'A',lambda *args,**kw:decision('verify_math',''))
 assert len(calls)==1 and result['tool_calls']==1 and result['model_calls']==3
 assert result['status']=='stopped' and result['stop_reason']=='decision_limit'


def test_unsupported_geometry_observation_can_escalate_without_fake_verification():
 w,s=workspace();s['question']='已知空间四边形，证明两直线垂直';s['steps']=['根据图形可知垂直'];s['answer']='垂直'
 def model(system,user,**kw):
  data=json.loads(user)
  if not data['observations']:return decision('verify_math','',step=None,evidence_ids=['QUESTION'])
  key=next(iter(data['observations']));assert data['observations'][key]['status']=='not_applicable'
  return decision('request_teacher','当前工具无法验证这段空间几何证明，请教师核对条件。',step=None,evidence_ids=['QUESTION',key])
 result=a.run(w,s['id'],'A',model)
 assert result['status']=='escalated' and not w['reviews']


def test_quota_resume_keeps_successful_tool_result_and_no_partial_answer_is_published(tmp_path):
 w,s=workspace();calls=[]
 def first(*args,**kw):
  calls.append(1)
  if len(calls)==2:raise UsageLimitError('限流')
  return decision('verify_math','')
 paused=a.run(w,s['id'],'A',first)
 assert paused['status']=='paused' and paused['tool_calls']==1 and not w['study_sessions'][0]['turns']
 path=tmp_path/'w.json';c.save(w,path);loaded=c.load(path)
 def resume(system,user,**kw):
  data=json.loads(user);assert data['observations']
  return decision('explain_step','复用已完成的局部核验，解释原第二步。')
 result=a.run(loaded,s['id'],'A',resume,resume=True)
 assert result['status']=='delivered' and result['tool_calls']==1 and result['model_calls']==3
 assert len(loaded['study_sessions'][0]['turns'])==1


def test_service_error_is_recorded_without_echoing_transport_secrets():
 w,s=workspace()
 def broken(*args,**kw):raise RuntimeError('do-not-store-this-sensitive-transport-string')
 result=a.run(w,s['id'],'A',broken)
 assert result['status']=='failed' and 'do-not-store' not in json.dumps(w)
 assert not w['study_sessions'][0]['turns']


def test_input_budget_stops_before_network_and_foreign_student_is_rejected():
 w,s=workspace();s['question']='题'*4000;s['steps']=['步'*4000,'步'*4000];s['answer']='答'*2000
 result=a.run(w,s['id'],'A',lambda *args,**kw:pytest.fail('Oversized input reached model'),reply='问'*2000)
 assert result['stop_reason']=='input_limit'
 with pytest.raises(ValueError):a.run(w,s['id'],'B',lambda *args,**kw:pytest.fail('Wrong student'))


def test_practice_requires_consent_then_validated_reference_and_tracks_answer_reveal():
 w,s=workspace()
 with pytest.raises(ValueError):a.accept_practice(w,s['id'],'A',exercise)
 a.run(w,s['id'],'A',lambda *args,**kw:decision('offer_practice','愿意用一道新题检查分配律吗？'))
 practice=a.accept_practice(w,s['id'],'A',exercise)
 assert practice and practice['learning']['exercise']['reference_tool']['final_answer_status']=='correct'
 assert a.accept_practice(w,s['id'],'A',lambda *args,**kw:pytest.fail('Duplicate generation')) is practice
 practice['learning']['exercise']['answer_revealed']=True
 item=a.check_practice(w,s['id'],'A','x=1','-2*x+8=6\n-2*x=-2\nx=1',grade)
 assert not item['independent'] and not w['attempts']
 def next_decision(system,user,**kw):
  assert json.loads(user)['sources']['PRACTICE_LAST']['independent'] is False
  return decision('finish','本题在看过参考解后完成，还需要独立的新证据。',evidence_ids=['PRACTICE_LAST'])
 assert a.run(w,s['id'],'A',next_decision,reply='继续查看练习结果')['status']=='completed'


def test_wrong_practice_reference_is_not_published():
 w,s=workspace();a.run(w,s['id'],'A',lambda *args,**kw:decision('offer_practice','是否自愿练习？'))
 def wrong(*args,**kw):
  payload=exercise(*args,**kw);payload['answer']='x=99';return payload
 assert a.accept_practice(w,s['id'],'A',wrong) is None
 assert a.latest_run(w,s['id'],'A').get('practice_error')


def test_agent_and_trace_persist_through_scoped_classroom_storage(tmp_path):
 teacher=x.create('受控辅导课堂',tmp_path);base=x.load(teacher,tmp_path);w=deepcopy(base)
 p.create_batch(w,'原题',[dict(CASES[10],student_id='A')]);x.save(teacher,base,w,tmp_path)
 student=x.invite(teacher,'A',tmp_path);base=x.load(student,tmp_path);own=deepcopy(base);s=own['submissions'][0]
 a.run(own,s['id'],'A',lambda *args,**kw:decision('request_teacher','请核对本题条件与原始步骤。'))
 x.save(student,base,own,tmp_path)
 teacher_view=x.load(teacher,tmp_path)
 assert a.latest_run(teacher_view,s['id'],'A')['status']=='escalated'
 assert not teacher_view['reviews'] and not teacher_view['learning']


def test_tool_failure_is_an_observation_not_a_claimed_pass(monkeypatch):
 w,s=workspace()
 def broken(*args,**kw):raise RuntimeError('private-tool-error')
 monkeypatch.setattr(a.math_tools,'evidence',broken)
 def model(system,user,**kw):
  data=json.loads(user)
  if not data['observations']:return decision('verify_math','')
  assert next(iter(data['observations'].values()))['status']=='failed'
  return decision('request_teacher','局部核验没有完成，请教师核对原步骤。')
 result=a.run(w,s['id'],'A',model)
 assert result['status']=='escalated' and result['tool_calls']==1
 assert 'private-tool-error' not in json.dumps(w)

def test_two_distinct_verifications_obey_tool_budget():
 w,s=workspace()
 def model(system,user,**kw):
  observations=json.loads(user)['observations']
  if not observations:return decision('verify_math','')
  if len(observations)==1:return decision('verify_math','',target='reply',evidence_ids=['REPLY'])
  return decision('explain_step','结合原步骤和你刚才的等式，说明相邻变形的依据。')
 result=a.run(w,s['id'],'A',model,reply='x=2')
 assert result['tool_calls']==2 and result['model_calls']==3 and result['status']=='delivered'


def test_switching_to_direct_does_not_delete_a_teacher_review_request():
 w,s=workspace();result=a.run(w,s['id'],'A',lambda *args,**kw:decision('request_teacher','需要核对原题条件。'))
 a.cancel(w,s['id'],'A')
 assert result['status']=='cancelled' and result['needs_teacher_review'] and not w['reviews']


def test_same_subject_concurrent_execution_is_rejected_before_second_request():
 from concurrent.futures import ThreadPoolExecutor
 from threading import Event
 w,s=workspace();entered=Event();release=Event();calls=[]
 def slow(*args,**kw):
  calls.append(1);entered.set();assert release.wait(timeout=5)
  return decision('explain_step','逐项说明分配律。')
 with ThreadPoolExecutor(max_workers=1) as pool:
  first=pool.submit(a.run,w,s['id'],'A',slow)
  assert entered.wait(timeout=5)
  try:
   with pytest.raises(RuntimeError,match='正在处理'):a.run(deepcopy(w),s['id'],'A',slow)
  finally:release.set()
  assert first.result()['status']=='delivered'
 assert len(calls)==1


def test_stale_browser_resume_refreshes_under_subject_lease_without_repeating_call():
 w,s=workspace()
 def limit(*args,**kw):raise UsageLimitError('暂时限流')
 a.run(w,s['id'],'A',limit);stale=deepcopy(w)
 a.run(w,s['id'],'A',lambda *args,**kw:decision('explain_step','请求已恢复。'),resume=True)
 with pytest.raises(ValueError,match='没有可继续'):
  a.run(stale,s['id'],'A',lambda *args,**kw:pytest.fail('Stale resume made a new request'),resume=True,_prepare=lambda:w)


def test_student_cancel_during_request_prevents_following_tools(monkeypatch):
 from concurrent.futures import ThreadPoolExecutor
 from threading import Event
 w,s=workspace();entered=Event();release=Event()
 def slow(*args,**kw):
  entered.set();assert release.wait(timeout=5);return decision('verify_math','')
 monkeypatch.setattr(a.math_tools,'evidence',lambda *args:pytest.fail('A cancelled action executed'))
 with ThreadPoolExecutor(max_workers=1) as pool:
  future=pool.submit(a.run,w,s['id'],'A',slow)
  assert entered.wait(timeout=5)
  a.cancel(deepcopy(w),s['id'],'A');release.set()
  result=future.result()
 assert result['status']=='cancelled' and result['tool_calls']==0


def test_new_teacher_evidence_invalidates_same_input_cache():
 from test_product import quick,deep
 w,s=workspace();p.quick_check(s,lambda *args,**kw:quick(s));p.deep_analyze(s,lambda *args,**kw:deep(s))
 calls=[]
 def model(*args,**kw):calls.append(1);return decision('explain_step','根据当前教师意见核对这一步。')
 first=a.run(w,s['id'],'A',model,reply='请解释第二步')
 assert a.run(w,s['id'],'A',model,reply='请解释第二步')['id']==first['id']
 c.review(w,s['id'],'confirm','教师补充',[],'新的教学依据','new-review',first_error_step=2)
 second=a.run(w,s['id'],'A',model,reply='请解释第二步')
 assert second['id']!=first['id'] and len(calls)==2
 assert second['trace'][0]['teacher_review_id']==w['reviews'][-1]['id']
