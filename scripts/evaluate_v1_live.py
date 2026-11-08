"""Bounded, opt-in real-model evaluation. Never prints credentials."""
import argparse
import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime,timezone
from PIL import Image,ImageDraw,ImageFont
sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core import ai,education as e,classroom as c
from core.usage import for_session

for name in ('openai','httpx','httpcore'):
    logging.getLogger(name).setLevel(logging.WARNING)
parser=argparse.ArgumentParser()
parser.add_argument('--suite',choices=['math','vision','learning','baseline'],required=True)
parser.add_argument('--count',type=int,default=10)
parser.add_argument('--offset',type=int,default=0)
args=parser.parse_args()
OUT=ROOT/'artifacts'/'v1-live'
OUT.mkdir(parents=True,exist_ok=True)
CASES=json.loads((ROOT/'data/highschool_examples.json').read_text(encoding='utf-8-sig'))
session='v1-live-'+args.suite
report={'date':datetime.now(timezone.utc).isoformat(),'suite':args.suite,'checks':[],
        'notice':'Constructed anonymous materials with reference labels, not an independently teacher-labeled dataset or real handwriting benchmark.'}

def call(system,user,**kwargs):
    return ai.completion([{'role':'system','content':system},{'role':'user','content':user}],session_id=session,**kwargs)

def write():
    report['usage']=for_session(session)
    suffix='-extra-'+str(args.offset) if args.offset else ''
    (OUT/(args.suite+suffix+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

def run(name,fn):
    started=time.monotonic()
    try:
        item=fn()
        row={'name':name,'status':'completed','elapsed_seconds':round(time.monotonic()-started,2),'result':item}
    except (RuntimeError,ValueError) as exc:
        row={'name':name,'status':'failed','elapsed_seconds':round(time.monotonic()-started,2),'error':str(exc)}
    except Exception as exc:
        row={'name':name,'status':'failed','error_type':type(exc).__name__}
    report['checks'].append(row);write()
    print(json.dumps({k:v for k,v in row.items() if k!='result'},ensure_ascii=False),flush=True)
    return row

if not ai.ai_ready():
    print('NOT_READY: server configuration unavailable; no paid request was sent.')
    raise SystemExit(2)

if args.suite in ('math','baseline'):
    selected_cases=CASES[max(0,args.offset):max(0,args.offset)+max(0,min(args.count,14))]
    for case in selected_cases:
        sub=e.normalize_submission(case,'live_constructed_fixture')
        def evaluate(sub=sub,case=case):
            if args.suite=='math':
                rec=e.analyze_submission(sub,call)
                if rec['status']!='completed':
                    raise ValueError(rec['error'])
                analysis=rec['analysis']
            else:
                raw={k:sub[k] for k in ('question','steps','answer','topic','task_type')}
                analysis=call(e.ANALYSIS_PROMPT,json.dumps(raw,ensure_ascii=False),purpose='baseline',max_tokens=5000,json_output=True)
                rec={'raw_analysis':analysis}
            expected=case['gold']
            return {'question_no':case['question_no'],'topic':case['topic'],'record':rec,
                    'reference':expected,'overall_match':analysis.get('overall')==expected['overall'],
                    'first_error_match':analysis.get('first_error_step')==expected['first_error_step'],
                    'final_answer_match':analysis.get('final_answer_status')==expected['final']}
        run(case['question_no'],evaluate)
        # Keep under the same 6/min session admission policy as the UI.
        if case!=selected_cases[-1]:
            time.sleep(11)

elif args.suite=='vision':
    font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',30)
    small=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',24)
    for index,selected in enumerate(([CASES[0],CASES[4]],[CASES[7]]),1):
        image=Image.new('RGB',(1400,1500),'white')
        draw=ImageDraw.Draw(image)
        draw.text((55,30),'构造印刷数学识别测试 · 非真实学生手写',font=small,fill='#6a776b')
        y=100
        for case in selected:
            for line in ['匿名编号 '+case['student_id']+'   '+case['question_no'],case['question']]+case['steps']+['最终答案：'+case['answer']]:
                draw.text((55,y),line,font=font,fill='#122b25');y+=60
            y+=55
        if index==2:
            # Schematic box, visibly labeled, not used as an unstated proof condition.
            points=[(420,900),(820,900),(960,800),(560,800),(420,1170),(820,1170),(960,1070),(560,1070)]
            for a,b in ((0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)):
                draw.line([points[a],points[b]],fill='#354e6b',width=4)
            for point,label in zip(points,['A1','B1','C1','D1','A','B','C','D']):
                draw.text((point[0]-25,point[1]+5),label,font=small,fill='black')
        path=OUT/f'printed_fixture_{index}.png';image.save(path)
        def recognize(path=path,selected=selected):
            result=e.extract_image(path.read_bytes(),call)
            return {'fixture':str(path),'kind':'constructed printed image, not handwriting','draft':result,
                    'expected_anonymous_ids':[x['student_id'] for x in selected],
                    'all_ids_recovered':set(x['student_id'] for x in selected)<=set(r['student_id'] for r in result['records']),
                    'records_count':len(result['records'])}
        run('printed-image-'+str(index),recognize)
        time.sleep(11)

elif args.suite=='learning':
    path=OUT/'math.json'
    previous=json.loads(path.read_text(encoding='utf-8'))
    selected=next(x for x in previous['checks'] if x['name']=='Q05' and x['status']=='completed')
    sub=e.normalize_submission(CASES[4],'live_constructed_fixture')
    sub['analyses']=[selected['result']['record']]
    w=c.new_workspace();w['submissions'].append(sub)
    c.review(w,sub['id'],'confirm','除以负数时不等号未反向',['不等式同解变形'],'先区分方向规则与运算疏忽','live-review',first_error_step=1)
    task=c.assign(w,sub['id'],'能说明负数乘除时的方向变化，并独立解结构变化的不等式','deep','live-task')
    sub=w['submissions'][0]
    learning=e.new_learning(task,sub);w['learning'].append(learning)
    task['status']='in_progress'
    run('diagnostic-question',lambda:e.tutor_turn(learning,task,sub,'question','',call,'live-q'))
    time.sleep(11)
    run('adaptive-reply',lambda:e.tutor_turn(learning,task,sub,'reply','我以为不等式两边做同样的除法就不用改方向。',call,'live-r'))
    time.sleep(11)
    ex=run('targeted-exercise',lambda:e.generate_exercise(learning,task,sub,call))
    if ex['status']=='completed':
        # Reference-answer replay is pipeline smoke only, NOT student learning success.
        learning['exercise']['answer_revealed']=True
        time.sleep(11)
        result=run('reference-replay-grading',lambda:e.grade_attempt(learning,task,ex['result']['answer'],'',call,w['attempts']))
        if result['status']=='completed':
            result['result']['benchmark_note']='Reference answer supplied by test code; not an independent human student attempt.'
            w['attempts'].append(result['result'])
            write()
    learning['ended'],learning['stage']=True,'completed'
    task['status']='completed'
    c.save(w,OUT/'constructed_loop_workspace.json')
    report['closed_loop_state']=e.learning_state(w['attempts'])
    report['closed_loop_notice']='API pipeline smoke with constructed material and reference replay, not proof of learning effectiveness.'
    write()
print('Finished; only redacted educational responses and usage metadata were saved.',flush=True)

