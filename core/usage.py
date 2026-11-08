"""Bounded request metadata only: no prompts, responses, images or credentials."""
from collections import deque
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

