"""Single-process, thread-safe AI admission limits. No keys or input are stored."""
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
import math
import time

from core.settings import integer_setting


class UsageLimitError(RuntimeError):
    def __init__(self, message, *, retry_after=None, reason=None):
        super().__init__(message)
        self.retry_after=retry_after
        self.reason=reason


def auto_resume(call, notify, *, max_wait=120, sleep=time.sleep):
    """Resume an explicitly started operation only for short, known limits."""
    remaining=max_wait
    def request(*args, **kwargs):
        nonlocal remaining
        provider_retries=0
        while True:
            try:
                return call(*args, **kwargs)
            except UsageLimitError as exc:
                delay=exc.retry_after
                if delay is None or not math.isfinite(delay) or delay>remaining:
                    raise
                if exc.reason=='provider':
                    if provider_retries>=2:
                        raise
                    provider_retries+=1
                delay=max(1,delay)
                if delay>remaining:
                    raise
                remaining-=delay
                seconds=int(delay)
                while seconds>0:
                    notify(exc.reason,seconds)
                    sleep(1)
                    seconds-=1
                if delay%1:
                    sleep(delay%1)
                notify(exc.reason,0)
    return request


@dataclass(frozen=True)
class Limits:
    session_minute: int = 6
    session_day: int = 50
    global_minute: int = 30
    global_day: int = 300
    daily_units: int = 2000000
    concurrent: int = 2

    @classmethod
    def configured(cls):
        return cls(**{name: integer_setting('MINDTRACE_' + name.upper(), field.default)
                      for name, field in cls.__dataclass_fields__.items()})


class UsageLimiter:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = Lock()
        self.day = None
        self.sessions = {}
        self.minute = deque()
        self.day_count = 0
        self.units = 0
        self.active = 0

    @contextmanager
    def request(self, session_id, units, limits):
        if not isinstance(session_id, str) or not 1 <= len(session_id) <= 100 or units <= 0:
            raise ValueError('请求标识或预算无效。')
        with self.lock:
            now = self.clock()
            day = datetime.fromtimestamp(now, timezone.utc).date()
            if self.day != day:
                self.day, self.sessions, self.minute = day, {}, deque()
                self.day_count, self.units = 0, 0
            while self.minute and self.minute[0] <= now - 60:
                self.minute.popleft()
            state = self.sessions.get(session_id, {'minute': deque(), 'day': 0})
            while state['minute'] and state['minute'][0] <= now - 60:
                state['minute'].popleft()
            if (state['day'] >= limits.session_day or self.day_count >= limits.global_day
                    or self.units + units > limits.daily_units):
                raise UsageLimitError('今日 AI 额度已用完。已保存进度，请在额度恢复后继续。',reason='daily')
            if not min(limits.session_minute,limits.global_minute,limits.concurrent):
                raise UsageLimitError('当前 AI 服务调用额度已关闭，请联系演示提供者。',reason='disabled')
            waits=[queue[-limit]+60-now for queue,limit in (
                (state['minute'],limits.session_minute),(self.minute,limits.global_minute)) if len(queue)>=limit]
            if waits:
                raise UsageLimitError('AI 操作较频繁，已达到短时请求上限。',retry_after=max(waits)+.05,reason='minute')
            if self.active >= limits.concurrent:
                raise UsageLimitError('AI 服务当前繁忙。',retry_after=3,reason='busy')
            state['minute'].append(now)
            state['day'] += 1
            self.sessions[session_id] = state
            self.minute.append(now)
            self.day_count += 1
            self.units += units
            self.active += 1
        try:
            yield
        finally:
            with self.lock:
                self.active -= 1


LIMITER = UsageLimiter()


def request_units(messages, max_tokens, *, output_limit=5000):
    """Bound input before any API attempt. Units are reservations, not billing."""
    if type(max_tokens) is not int or not 1 <= max_tokens <= output_limit:
        raise ValueError('单次输出长度超出限制。')
    if not isinstance(messages, list) or not 1 <= len(messages) <= 24:
        raise ValueError('对话条数超出限制。')
    text_bytes, images, image_bytes = 0, 0, 0
    for message in messages:
        if not isinstance(message, dict) or message.get('role') not in ('system', 'user', 'assistant'):
            raise ValueError('对话格式无效。')
        content = message.get('content')
        if isinstance(content, str):
            text_bytes += len(content.encode('utf-8'))
        elif isinstance(content, list):
            if len(content) > 4:
                raise ValueError('单次内容块过多。')
            for block in content:
                if not isinstance(block, dict):
                    raise ValueError('内容块无效。')
                if block.get('type') == 'text' and isinstance(block.get('text'), str):
                    text_bytes += len(block['text'].encode('utf-8'))
                elif block.get('type') == 'image_url':
                    image = block.get('image_url')
                    if not isinstance(image, dict):
                        raise ValueError('图片内容块无效。')
                    url = image.get('url', '')
                    if not isinstance(url, str) or not url.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
                        raise ValueError('只接受经过校验的内嵌图片。')
                    images += 1
                    image_bytes += len(url)
                else:
                    raise ValueError('不支持的内容块。')
        else:
            raise ValueError('对话内容无效。')
    if text_bytes > 64000 or images > 1 or image_bytes > 12 * 1024 * 1024:
        raise ValueError('单次请求内容过大，请缩短对话或分图提交。')
    return max_tokens + text_bytes + images * 16384

