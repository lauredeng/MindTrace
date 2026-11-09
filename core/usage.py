"""Bounded request metadata only: no prompts, responses, images or credentials."""
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4
import time
import math

_EVENTS = deque(maxlen=2000)
_LOCK = Lock()


def record(session_id, purpose, model, response, started, status, retry_index, cfg):
    usage = getattr(response, 'usage', None)
    prompt = getattr(usage, 'prompt_tokens', None)
    output = getattr(usage, 'completion_tokens', None)
    estimate = None
    try:
        if prompt is not None and output is not None and cfg.get('input_price') and cfg.get('output_price'):
            incoming, outgoing = float(cfg['input_price']), float(cfg['output_price'])
            if math.isfinite(incoming) and math.isfinite(outgoing) and incoming >= 0 and outgoing >= 0:
                estimate = round((prompt * incoming + output * outgoing) / 1000000, 6)
    except (TypeError, ValueError):
        pass
    event = {'id': str(uuid4()), 'session_id': session_id,
             'created_at': datetime.now(timezone.utc).isoformat(), 'purpose': purpose,
             'model': str(getattr(response, 'model', None) or model), 'status': status,
             'elapsed_seconds': round(time.monotonic() - started, 3), 'retry_index': retry_index,
             'prompt_tokens': prompt, 'completion_tokens': output,
             'estimated_cost': estimate, 'currency': cfg.get('currency', 'CNY'),
             'cost_basis': 'configured rates, cache discounts not modeled' if estimate is not None else 'price or usage not configured'}
    key = cfg.get('key')
    if key:
        event = {name: value.replace(key, '[凭据已隐藏]') if isinstance(value, str) else value for name, value in event.items()}
    with _LOCK:
        _EVENTS.append(event)


def for_session(session_id):
    with _LOCK:
        return [dict(event) for event in _EVENTS if event['session_id'] == session_id]



def by_purpose(events):
    groups=defaultdict(list)
    for event in events:
        groups[event['purpose']].append(event)
    results=[]
    for purpose,group in sorted(groups.items()):
        counts=Counter(event['status'] for event in group)
        costed=[event for event in group if event.get('estimated_cost') is not None]
        results.append({
            'purpose':purpose,'requests':len(group)-counts['blocked'],'completed':counts['completed'],
            'truncated':counts['truncated'],'invalid_json':counts['invalid_json'],'blocked':counts['blocked'],
            'prompt_tokens':sum(event.get('prompt_tokens') or 0 for event in group),
            'completion_tokens':sum(event.get('completion_tokens') or 0 for event in group),
            'request_seconds':round(sum(event.get('elapsed_seconds',0) for event in group if event['status']!='blocked'),2),
            'estimated_cost':round(sum(event['estimated_cost'] for event in costed),6) if costed and
                len({event.get('currency') for event in costed})==1 else None,
            'priced_responses':len(costed),
        })
    return results
