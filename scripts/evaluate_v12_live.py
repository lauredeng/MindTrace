"""Opt-in actual V1.2 API smoke on constructed anonymous materials, not student outcomes."""
import json,os,sys,time
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['MINDTRACE_ENV']='development'
from core import product as p,education as e,classroom as c,ai
from core.usage import for_session
ROOT=Path.cwd();OUT=ROOT/'artifacts/v12-live';OUT.mkdir(parents=True,exist_ok=True)
session='v12-live-20261107'
report={'material':'developer-constructed anonymous mathematics; reference operations are test actions','checks':[]}
path=OUT/'workspace.json'
if path.exists():
    w=c.load(path);batch=w['batches'][0]
    if (OUT/'report.json').exists():
        report=json.loads((OUT/'report.json').read_text(encoding='utf-8'))
else:
    cases=json.loads((ROOT/'data/highschool_examples.json').read_text(encoding='utf-8-sig'))
    wrong=dict(cases[10],student_id='V12-A')
    other=dict(cases[10],student_id='V12-B')
    correct=dict(cases[10],student_id='V12-C',steps=['x+3=5','x=2'],answer='x=2')
    w=c.new_workspace();batch=p.create_batch(w,'V1.2真实接口 · 构造匿名方程',[wrong,other,correct],'v12_constructed_live')
last=[0]
def call(system,user,**kw):
    delay=max(0,12-(time.monotonic()-last[0]))
    if delay:time.sleep(delay)
    last[0]=time.monotonic()
    result=ai.completion([{'role':'system','content':system},{'role':'user','content':user}],session_id=session,**kw)
    print('Actual request completed:',kw.get('purpose'),flush=True)
    return result
def save():
    ids={v['id'] for v in w['usage']}
    w['usage'].extend(v for v in for_session(session) if v['id'] not in ids)
    c.save(w,path)
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
def progress(stage,i,n):
    save();print('Batch progress',stage,i,n,flush=True)
p.run_batch(w,batch['id'],call,progress)
report['checks'].append({'name':'three-pupil-shared-question-two-layer-batch','result':p.per_question(w,batch['id'])})
save()
no_work=next((s for s in w['submissions'] if s['student_id']=='V12-SELF'),None)
if not no_work:
    no_work=e.normalize_submission({'student_id':'V12-SELF','question_no':'T01','topic':'三角函数',
        'question':'已知 sin α=3/5，α为第一象限角，求 sin(2α)。','steps':[],'answer':''},'self_study',allow_unanswered=True)
    w['submissions'].append(no_work)
result=p.solve_question(no_work,'full',call)
report['checks'].append({'name':'unanswered-direct-full-solution','status':result['status']})
save()
try:
    if not any(s['submission_id']==no_work['id'] for s in w['study_sessions']):
        p.study_turn(w,no_work,'reply','为什么求 cos α 时这里取正根？',call)
    report['checks'].append({'name':'free-follow-up','status':'completed'})
except (RuntimeError,ValueError) as exc:
    report['checks'].append({'name':'free-follow-up','status':'failed','error':str(exc)})
save()
wrong=next(s for s in w['submissions'] if s['student_id']=='V12-A')
# Explicit test self-report, not a claim of actual cognitive cause.
result=p.solve_question(wrong,'full',call,cause='公式或定理遗忘')
item=p.sync_notebook(w,wrong['id'],True,'公式或定理遗忘')
p.edit_entry(w,item['id'],'公式或定理遗忘',[],'构造测试：模拟本人确认分类，不是实际学生学习证据。',True)
report['checks'].append({'name':'formula-and-conditions-in-notebook','status':result['status'],'supplements':len(item['supplements'])})
save()
fixture=ROOT/'artifacts/v1-live/printed_fixture_1.png'
if fixture.exists():
    try:
        draft=e.extract_image(fixture.read_bytes(),call)
        (OUT/'vision.json').write_text(json.dumps(draft,ensure_ascii=False,indent=2),encoding='utf-8')
        report['checks'].append({'name':'printed-vision','status':'completed','records':len(draft['records']),
            'note':'generated printed image, not handwritten student work'})
    except (RuntimeError,ValueError) as exc:
        report['checks'].append({'name':'printed-vision','status':'failed','error':str(exc)})
save()
print('Finished actual smoke. Calls recorded:',len(for_session(session)),flush=True)

