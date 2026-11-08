"""Agent UI interactions use explicit offline decisions and real local mathematics."""
import json
from core import ai,product as p,agent as a
from test_product_ui import app,click
from test_agent import decision
from test_education import CASES


def test_deep_tutoring_selects_tools_keeps_sources_and_can_switch_to_direct(app,monkeypatch):
 at,calls=app;click(at,'进入教师工作台')
 w=at.session_state['studio_workspace'];p.create_batch(w,'受控辅导界面',[CASES[10]])
 at.run();click(at,'开始批改并分析错题')
 click(at,'返回产品首页');click(at,'进入学生学习中心')
 sub=at.session_state['studio_workspace']['submissions'][0]
 normal=ai.completion;decisions=[]
 def model(messages,**kw):
  if kw['purpose']!='agent_decision':return normal(messages,**kw)
  context=json.loads(messages[1]['content']);decisions.append(context)
  if not context['sources'].get('REPLY'):return decision()
  if not context['observations']:return decision('verify_math','',evidence_ids=['S2','REPLY'])
  key=next(iter(context['observations']))
  return decision('explain_step','两项都要乘2，局部核验显示原第二步不等价。',evidence_ids=['S2',key],verification_claim='local_checked')
 monkeypatch.setattr(ai,'completion',model)
 at.session_state['tutoring_mode_'+sub['id']]='深度辅导';at.run()
 click(at,'开始深度辅导')
 assert any('等待你的回答' in item.value for item in at.info)
 next(t for t in at.text_area if t.label=='回答或补充你的问题').set_value('我以为只有x需要乘2')
 click(at,'发送并继续辅导')
 run=a.latest_run(at.session_state['studio_workspace'],sub['id'],sub['student_id'])
 assert run['status']=='delivered' and run['tool_calls']==1 and len(decisions)==3
 assert at.session_state['studio_workspace']['submissions'][0]['steps']==CASES[10]['steps']
 at.session_state['tutoring_mode_'+sub['id']]='直接答疑';at.run()
 assert not at.exception
 assert a.latest_run(at.session_state['studio_workspace'],sub['id'],sub['student_id'])['status']=='cancelled'
 assert any(b.label=='获取所选讲解' for b in at.button)
 assert len(decisions)==3


def test_agent_request_for_teacher_appears_in_existing_feedback(app,monkeypatch):
 at,calls=app;click(at,'进入教师工作台')
 w=at.session_state['studio_workspace'];p.create_batch(w,'需要复核',[CASES[10]])
 at.run();click(at,'开始批改并分析错题')
 click(at,'返回产品首页');click(at,'进入学生学习中心')
 sub=at.session_state['studio_workspace']['submissions'][0]
 monkeypatch.setattr(ai,'completion',lambda *args,**kw:decision('request_teacher','请教师核对第2步和原题条件。'))
 at.session_state['tutoring_mode_'+sub['id']]='深度辅导';at.run();click(at,'开始深度辅导')
 click(at,'教师')
 assert any('本题已请求教师核对' in item.value for item in at.warning)
 assert not at.exception
