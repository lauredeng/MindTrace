"""Explicit opt-in, one real upstream teaching turn; never auto-retry billing."""
import argparse
import json
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--case',choices=['source','math'],default='source')
    args=parser.parse_args()
    import httpx
    from websockets.sync.client import connect
    from scripts.prepare_tutor_fixture import prepare
    fixture=prepare();out=ROOT/'artifacts'/'deeptutor';out.mkdir(parents=True,exist_ok=True)
    api='http://127.0.0.1:8591'
    with httpx.Client(base_url=api,trust_env=False,timeout=60) as client:
        ticket=client.post('/api/mindtrace/tickets',headers={'Authorization':'Bearer '+fixture['student_code']},
                           json={'submission_id':fixture['submission_id']})
        ticket.raise_for_status()
        client.post('/api/mindtrace/connect',json={'ticket':ticket.json()['ticket']}).raise_for_status()
        lesson=client.post('/api/mindtrace/open',json={'submission_id':fixture['submission_id']})
        lesson.raise_for_status();lesson=lesson.json()
        cookie='; '.join(k+'='+v for k,v in client.cookies.items())
    command={'type':'start_turn','protocol_version':'2.0','session_id':lesson['session_id'],
        'client_submission_id':uuid.uuid4().hex,'capability':'mastery_path','language':'zh',
        'mastery_path_id':lesson['path_id'],'mastery_session_mode':'study',
        'content':'请结合本题原始作答和教师反馈，直接说明我求导时漏掉了什么、为什么驻点在定义域内，以及为什么这是全局最大值。先不要出新题，不要推断我已经掌握。'}
    if args.case=='math':
        command['content']='请实际调用mindtrace_math，分别核验sin(x)^2+cos(x)^2、log(x)-a*x的导数、binomial(10,3)/2^10，展示精确结果与适用条件。需要时先用load_tools加载该工具。不要出题，不要改变我的掌握状态。'
    events=[];started=time.monotonic();turn_id=None
    with connect('ws://127.0.0.1:8591/ws',additional_headers={'Cookie':cookie},
                 origin='http://127.0.0.1:8592',open_timeout=30,proxy=None) as ws:
        ws.send(json.dumps(command,ensure_ascii=False))
        try:
            while time.monotonic()-started<180:
                item=json.loads(ws.recv(timeout=min(30,180-(time.monotonic()-started))))
                events.append(item);turn_id=item.get('turn_id') or turn_id
                if item.get('type') in ('done','protocol_error'):break
        except TimeoutError:
            if turn_id:
                ws.send(json.dumps({'type':'cancel_turn','protocol_version':'2.0',
                    'turn_id':turn_id,'command_id':uuid.uuid4().hex}))
            raise RuntimeError('Teaching did not finish within the bounded live check; cancellation requested.') from None
        finally:
            (out/('live-turn.json' if args.case=='source' else 'live-math-turn.json')).write_text(json.dumps({'route':lesson['route'],'elapsed_seconds':round(time.monotonic()-started,2),
                'synthetic_classroom_fixture':True,'real_provider_turn':True,'events':events},ensure_ascii=False,indent=2),encoding='utf-8')
    failures=[x for x in events if x.get('type') in ('error','protocol_error')]
    results=[x for x in events if x.get('type')=='result']
    print(json.dumps({'events':len(events),'results':len(results),'errors':len(failures),
                      'elapsed_seconds':round(time.monotonic()-started,2)},ensure_ascii=True))
    if failures or not results:raise SystemExit('Live teaching failed; see the private local trace.')
    if args.case=='math':
        called=[e.get('content') for e in events if e.get('type')=='tool_call']
        if 'mindtrace_math' not in called:raise SystemExit('Model returned text but did not call the math tool.')


if __name__=='__main__':main()
