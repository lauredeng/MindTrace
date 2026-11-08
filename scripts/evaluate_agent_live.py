"""Small real-interface acceptance. At most two runs x three decisions; constructed inputs only."""
import json,sys
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core import ai,agent as a,classroom as c,education as e
from core.usage import for_session
OUT=ROOT/'artifacts/agent-live'/uuid4().hex;OUT.mkdir(parents=True)
source=json.loads((ROOT/'data/highschool_examples.json').read_text(encoding='utf-8-sig'))[10]
report={'material':'constructed anonymous algebra, not actual student handwriting','cases':[]}
if not ai.ai_ready():
 report['blocked']='Server-side AI configuration not ready; no requests made.'
else:
 for index,(reply,preference) in enumerate([
  ('我不确定2*x+3=10是否与原题等价，请先帮我核对再解释。','guided'),
  ('括号里的3不用乘2吗？这次请直接讲解，不要反问我。','direct')],1):
  w=c.new_workspace();sub=e.normalize_submission(dict(source,student_id='LIVE-CONSTRUCTED'));w['submissions'].append(sub)
  sid='agent-acceptance-'+uuid4().hex
  def call(system,user,**kwargs):
   return ai.completion([{'role':'system','content':system},{'role':'user','content':user}],session_id=sid,**kwargs)
  run=a.run(w,sub['id'],sub['student_id'],call,reply=reply,preference=preference)
  c.save(w,OUT/('case-'+str(index)+'.json'))
  events=for_session(sid)
  report['cases'].append({'preference':preference,'status':run['status'],'model_attempts':run['model_calls'],
   'tool_calls':run['tool_calls'],'actions':[t.get('action') for t in run['trace'] if t.get('policy')=='allowed'],
   'policy_rejections':sum(t.get('policy')=='rejected' for t in run['trace']),
   'real_request_events':len(events),'input_tokens':sum(v.get('prompt_tokens') or 0 for v in events),
   'output_tokens':sum(v.get('completion_tokens') or 0 for v in events)})
  if run['status'] in ('paused','failed'):break  # Do not spend further calls on a blocked service.
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'report':str(OUT/'report.json'),'result':report},ensure_ascii=True))
