"""Offline controller/browser fixture. Never a production fallback."""
import os,sys,runpy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
os.environ['MINDTRACE_ENV']='production';os.environ['MINDTRACE_SHARED_MODE']='1';os.environ['MINDTRACE_ENABLE_DEVELOPER_MODE']='0'
os.environ['MINDTRACE_DATA_DIR']=str(ROOT/'artifacts/agent-browser-fixture')
import streamlit as st
from core import ai,product as p,classroom as c
from core.limits import UsageLimitError
from test_agent import decision
from test_product import quick,deep,correction
from test_education import CASES,exercise,grade
st.warning('受控Agent隔离验收：模型决策为明确的离线模拟，数学工具实际执行，不代表模型准确率。')
scenario=st.selectbox('离线验收场景',['正常决策','工具后限流','越权动作'],key='agent_fixture_scenario')
def offline(messages,**kw):
 purpose=kw['purpose'];raw=json.loads(messages[1]['content'])
 if purpose=='quick_grading':return quick(raw)
 if purpose=='error_analysis':return deep(raw)
 if purpose=='agent_decision':
  sources=raw['sources'];reply=sources.get('REPLY','');observations=raw['observations']
  if scenario=='越权动作':return decision(action='execute_python')
  if scenario=='工具后限流' and observations:raise UsageLimitError('离线模拟限流')
  if raw['preference']=='direct':return decision('explain_step','直接讲解：括号中的两项都要乘2，得到2*x+6=10。',evidence_ids=['S2','REPLY'])
  if '请老师' in reply:return decision('request_teacher','需要教师核对原题条件与第二步的依据。',evidence_ids=['S2','REPLY'])
  if 'PRACTICE_LAST' in sources and '验证' in reply:return decision('finish','本次新题提供了有限的独立作答证据，后续仍需观察。',evidence_ids=['PRACTICE_LAST'])
  if '新题' in reply:return decision('offer_practice','愿意用一道自愿的新题检查分配律吗？',evidence_ids=['S2','REPLY'])
  if not reply:return decision()
  if not observations:return decision('verify_math','',evidence_ids=['S2','REPLY'])
  key=next(iter(observations))
  return decision('explain_step','局部工具显示第二步不等价。括号内每一项都应乘2，不能遗漏常数项。',evidence_ids=['S2',key],verification_claim='local_checked')
 if purpose=='exercise':return exercise()
 if purpose=='grading':return grade()
 if purpose=='solve_question':return {'known_conditions':[],'goal':'求x','method':'等价变形','correction':correction()}
 raise ValueError('Unexpected isolated purpose')
ai.ai_ready=lambda:True;ai.completion=offline
if 'studio_workspace' not in st.session_state:
 w=c.new_workspace();batch=p.create_batch(w,'受控辅导构造原题',[dict(CASES[10],student_id='A')],'offline_agent_fixture')
 def seed(system,user,**kw):return offline([{'role':'system','content':system},{'role':'user','content':user}],**kw)
 p.run_batch(w,batch['id'],seed);st.session_state['studio_workspace']=w
runpy.run_path(str(ROOT/'app.py'),run_name='__main__')
