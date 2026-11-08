"""Replay a complete reference solution; explicitly not an independent student."""
import json,sys,logging
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from core import ai,classroom as c,education as e
from core.usage import for_session
for name in ('openai','httpx','httpcore'):
    logging.getLogger(name).setLevel(logging.WARNING)
out=root/'artifacts/v1-live'
path=out/'constructed_loop_workspace.json'
w=c.load(path);task=w['tasks'][0];learning=w['learning'][0]
learning['ended']=False
ex=learning['exercise'];ex['answer_revealed']=True
session='v1-complete-reference'
def call(system,user,**kwargs):
    return ai.completion([{'role':'system','content':system},{'role':'user','content':user}],session_id=session,**kwargs)
try:
    item=e.grade_attempt(learning,task,ex['answer'],'\n'.join(ex['reference_steps']),call,w['attempts'])
    item['benchmark_note']='Complete reference-solution replay after viewing answer. Not an independent human learning result.'
    if not any(a['id']==item['id'] for a in w['attempts']):
        w['attempts'].append(item)
    learning['ended'],learning['stage']=True,'completed';task['status']='completed'
    c.save(w,path)
    report=json.loads((out/'learning.json').read_text(encoding='utf-8'))
    report['checks'].append({'name':'complete-reference-replay','status':'completed','result':item})
    report['usage'].extend(for_session(session));report['closed_loop_state']=e.learning_state(w['attempts'])
    (out/'learning.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'completed','overall':item['verdict'],'final_answer':item['final_answer_status'],
                      'independent':item['independent'],'learning_state':report['closed_loop_state']},ensure_ascii=False))
except (RuntimeError,ValueError) as exc:
    print('FAILED: '+str(exc))
    raise SystemExit(1)

