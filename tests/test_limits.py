from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import pytest
from core import ai
from core.limits import UsageLimiter, Limits, UsageLimitError, request_units
from core.workflow import make_run, import_run


def test_session_rate_and_minute_recovery():
    clock = [1700000000.0]
    guard = UsageLimiter(lambda: clock[0])
    limits = replace(Limits(), session_minute=1)
    with guard.request('one', 10, limits):
        pass
    with pytest.raises(UsageLimitError, match='频繁'):
        with guard.request('one', 10, limits):
            pass
    # Other visitors have independent per-session counters.
    with guard.request('two', 10, limits):
        pass
    clock[0] += 61
    with guard.request('one', 10, limits):
        pass


def test_global_budget_cannot_be_bypassed_with_new_session():
    guard = UsageLimiter()
    limits = replace(Limits(), global_day=1)
    with guard.request('one', 10, limits):
        pass
    with pytest.raises(UsageLimitError, match='额度'):
        with guard.request('new-browser', 10, limits):
            pass


def test_daily_units_and_utc_reset():
    clock = [1700000000.0]
    guard = UsageLimiter(lambda: clock[0])
    limits = replace(Limits(), daily_units=15)
    with guard.request('one', 10, limits):
        pass
    with pytest.raises(UsageLimitError):
        with guard.request('two', 10, limits):
            pass
    clock[0] += 86400
    with guard.request('one', 10, limits):
        pass
    assert guard.units == 10


def test_concurrency_and_failed_request_release():
    guard = UsageLimiter()
    limits = replace(Limits(), concurrent=1)
    with pytest.raises(ValueError):
        with guard.request('one', 10, limits):
            with pytest.raises(UsageLimitError, match='繁忙'):
                with guard.request('two', 10, limits):
                    pass
            raise ValueError('synthetic request failure')
    assert guard.active == 0
    assert guard.day_count == 1  # failures still consume reservations
    with guard.request('two', 10, limits):
        pass


def test_parallel_budget_admission_is_atomic():
    guard = UsageLimiter()
    limits = replace(Limits(), global_day=3, concurrent=10)
    def attempt(index):
        try:
            with guard.request(str(index), 10, limits):
                return True
        except UsageLimitError:
            return False
    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(attempt, range(20))) == 3
    assert guard.day_count == 3


@pytest.mark.parametrize('messages,max_tokens', [
    ([{'role': 'user', 'content': 'a' * 64001}], 100),
    ([{'role': 'user', 'content': 'ok'}], 5001),
    ([{'role': 'user', 'content': [{'type': 'image_url', 'image_url': 'bad'}]}], 100),
    ([{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'https://remote.invalid/image.png'}}]}], 100),
    ([{'role': 'user', 'content': 'ok'}] * 25, 100),
])
def test_input_bounds(messages, max_tokens):
    with pytest.raises(ValueError):
        request_units(messages, max_tokens)


def test_limit_blocks_before_transport(monkeypatch):
    monkeypatch.setattr(ai, 'config', lambda: {'key': 'synthetic-key', 'base_url': 'https://api.deepseek.com'})
    monkeypatch.setattr(ai.Limits, 'configured', lambda: replace(Limits(), global_day=0))
    def forbidden(**kwargs):
        raise AssertionError('No external attempt may occur after quota rejection')
    monkeypatch.setattr(ai, 'OpenAI', forbidden)
    with pytest.raises(UsageLimitError):
        ai.ask_ai('test', 'test')


def test_import_rechecks_math_and_discards_configuration():
    batch = make_run([{'student_id': 'S01', 'question': 'x**2', 'student_answer': '2*x'}], 'test')
    batch['results'][0]['status'] = 'incorrect'
    batch['api_key'] = 'SYNTHETIC-IGNORED-VALUE'
    batch['reviews'] = {'0': {'decision': '认可数学证据', 'note': '人工备注'}}
    imported = import_run(json.dumps(batch).encode())
    assert imported['results'][0]['status'] == 'correct'
    assert imported['reviews']['0']['note'] == '人工备注'
    assert 'SYNTHETIC-IGNORED-VALUE' not in json.dumps(imported)
    assert imported['id'] != batch['id']


@pytest.mark.parametrize('payload', [b'[]', b'{}', b'broken', b'a' * (1024 * 1024 + 1)])
def test_invalid_import(payload):
    with pytest.raises(ValueError):
        import_run(payload)
