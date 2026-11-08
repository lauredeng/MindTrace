"""Opt-in live text smoke check; never prints configuration or credentials."""
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for name in ('openai', 'httpx', 'httpcore'):
    logging.getLogger(name).setLevel(logging.WARNING)

from core.ai import ai_ready, completion, TEACHER_PROMPT, TUTOR_PROMPT

report = {'created_at': datetime.now(timezone.utc).isoformat(), 'checks': [],
          'scope': 'Real API text smoke checks with constructed anonymous math evidence; not handwriting accuracy evaluation.'}


def check(name, system, user, tokens=1800):
    started = time.monotonic()
    try:
        answer = completion([{'role': 'system', 'content': system},
                             {'role': 'user', 'content': user}],
                            max_tokens=tokens, session_id='authorized-local-smoke')
        item = {'name': name, 'status': 'passed', 'elapsed_seconds': round(time.monotonic()-started, 2),
                'response': answer}
        report['checks'].append(item)
        print(json.dumps({k: v for k, v in item.items() if k != 'response'}, ensure_ascii=False), flush=True)
        return answer
    except (RuntimeError, ValueError) as exc:
        item = {'name': name, 'status': 'failed', 'elapsed_seconds': round(time.monotonic()-started, 2),
                'error': str(exc)}
    except Exception as exc:
        # Unexpected errors must never dump request headers or configuration.
        item = {'name': name, 'status': 'failed', 'error': 'Unexpected error type: '+type(exc).__name__}
    report['checks'].append(item)
    print(json.dumps(item, ensure_ascii=False), flush=True)
    return None


if '--teacher-only' in sys.argv:
    previous = Path(__file__).resolve().parents[1] / 'artifacts' / 'live-text-report.json'
    if previous.exists():
        report = json.loads(previous.read_text(encoding='utf-8'))
    check('teacher_advice_page_budget', TEACHER_PROMPT,
          '人工构造匿名求导练习共12条：6条导数正确，5条学生答案等于外层求导部分但缺少内层导数，1条仅能确定结果不一致。请给出两条教学建议，并区分事实与待追问假设。', 1800)
elif not ai_ready():
    report['checks'].append({'name': 'server_configuration', 'status': 'not_ready',
                             'error': '服务端未能加载可用配置；未发送 API 请求。'})
    print(json.dumps(report['checks'][-1], ensure_ascii=False), flush=True)
else:
    reply = check('live_connection', '请用简短中文回答。', '请只回复：连接成功。', 400)
    if reply:
        check('teacher_advice', TEACHER_PROMPT,
              '人工构造匿名求导练习共12条：6条导数正确，5条学生答案等于外层求导部分但缺少内层导数，1条仅能确定结果不一致。请给出两条教学建议，并区分事实与待追问假设。')
        question = '题目：求 (3*x**2+1)**5 的导数。学生答案：5*(3*x**2+1)**4。独立数学证据：答案缺少内层导数因子。请先问一个诊断性问题，不直接给完整答案。'
        first = check('student_diagnostic_question', TUTOR_PROMPT, question)
        if first:
            check('student_adaptive_followup', TUTOR_PROMPT,
                  question+'\n上一轮追问：'+first+'\n学生新回答：我只求了外层导数，不知道为什么还要乘里面的导数。\n请根据这条新证据给一个简短提示，再提一个问题。')

out = Path(__file__).resolve().parents[1] / 'artifacts' / 'live-text-report.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('Report saved; no credential values included.', flush=True)

