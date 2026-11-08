import io
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from openai import OpenAI as RealOpenAI
from PIL import Image

from core.analyzer import analyze
from core.workflow import read_csv, make_run, make_exercise
from core.storage import load_runs, append_record, save_review
from core.ocr import prepare_image, recognize_image, validate_ocr
from core import ai, ocr

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('expr', [
    'x**999999999', '(x**12)**12', '1/0', 'x/x', 'x**-1',
    '__import__("os")', 'x.__class__', '[x]', 'True', '1e999', '(999999**12)**12',
])
def test_unsafe_or_out_of_scope(expr):
    assert analyze({'question': expr, 'student_answer': '0'}).status == 'unverified'


def test_demo_real_counts():
    run = make_run(read_csv((ROOT / 'data/demo.csv').read_bytes()), 'sample')
    assert run['count'] == 12
    assert sum(r['status'] == 'correct' for r in run['results']) == 6
    assert sum('遗漏内层导数' in r['label'] for r in run['results']) == 5
    assert all(r['status'] != 'unverified' for r in run['results'])


def test_exact_decimal_and_caret():
    assert analyze({'question': '0.1*x^2', 'student_answer': 'x/5'}).status == 'correct'


@pytest.mark.parametrize('data', [
    b'student_id,question\nA,x',
    b'student_id,question,student_answer\nA,x,',
    b'student_id,question,student_answer\n',
    b'student_id,question,student_answer\n' + b'A,x,1\n' * 101,
])
def test_invalid_csv(data):
    with pytest.raises(ValueError):
        read_csv(data)


def test_leading_zero_identifier():
    rows = read_csv(b'\xef\xbb\xbfstudent_id,question,student_answer\n001,x,1')
    assert rows[0]['student_id'] == '001'


def test_generated_exercises_are_verified():
    for seed in range(20):
        ex = make_exercise(seed)
        assert analyze({'question': ex['question'], 'student_answer': ex['answer']}).status == 'correct'


def test_idempotent_save_and_review(tmp_path):
    target = tmp_path / 'runs.json'
    run = make_run([{'student_id': 'A', 'question': 'x**2', 'student_answer': '2*x'}], 'test')
    append_record(run, target)
    append_record(run, target)
    assert len(load_runs(target)) == 1
    save_review(run['id'], 0, {'decision': '认可数学证据'}, target)
    assert load_runs(target)[0]['reviews']['0']['decision'] == '认可数学证据'


def test_corrupt_store_is_preserved(tmp_path):
    target = tmp_path / 'runs.json'
    target.write_text('broken original', encoding='utf-8')
    with pytest.raises(ValueError):
        append_record({'id': 'a'}, target)
    assert target.read_text(encoding='utf-8') == 'broken original'


def image_bytes():
    out = io.BytesIO()
    Image.new('RGB', (32, 32), 'white').save(out, format='PNG')
    return out.getvalue()


def test_invalid_images():
    with pytest.raises(ValueError):
        prepare_image(b'not an image')
    with pytest.raises(ValueError):
        prepare_image(b'a' * (8 * 1024 * 1024 + 1))


def test_ocr_sends_actual_image_and_requires_schema(monkeypatch):
    captured = {}
    def transport(messages, **kwargs):
        captured.update(messages=messages, kwargs=kwargs)
        return {'transcription': 'transport fixture only', 'warnings': [], 'records': []}
    monkeypatch.setattr(ocr, 'completion', transport)
    data = image_bytes()
    result = recognize_image(data)
    content = captured['messages'][1]['content']
    assert content[1]['image_url']['url'].startswith('data:image/png;base64,')
    assert captured['kwargs']['vision'] is True
    assert result['records'] == []
    assert len(result['image_sha256']) == 64
    with pytest.raises(ValueError):
        validate_ocr({'records': []})
    with pytest.raises(ValueError):
        validate_ocr({'transcription': 'text', 'warnings': [], 'records': [{'question': 'x'}]})


def test_openai_sdk_wire_compatibility(monkeypatch):
    captured = {}
    def respond(request):
        captured['path'] = request.url.path
        captured['body'] = json.loads(request.content)
        return httpx.Response(200, json={
            'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'deepseek-flash',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'protocol fixture'},
                         'finish_reason': 'stop'}],
        })
    monkeypatch.setattr(ai, 'config', lambda: {'key': 'test-key', 'base_url': 'https://api.deepseek.com',
                                              'model': 'deepseek-flash', 'vision_model': 'deepseek-flash'})
    monkeypatch.setattr(ai, 'OpenAI', lambda **kwargs: RealOpenAI(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond))))
    assert ai.ask_ai('test', 'test') == 'protocol fixture'
    assert captured['path'] == '/chat/completions'
    assert captured['body']['model'] == 'deepseek-flash'
    assert captured['body']['messages'][1]['content'] == 'test'


@pytest.mark.parametrize('code,fragment', [(401, '授权'), (402, '余额'), (429, '频繁'), (500, '暂时')])
def test_api_errors_redact_server_body(monkeypatch, code, fragment):
    monkeypatch.setattr(ai, 'config', lambda: {'key': 'test-key', 'base_url': 'https://api.deepseek.com',
                                              'model': 'deepseek-flash', 'vision_model': 'deepseek-flash'})
    monkeypatch.setattr(ai, 'OpenAI', lambda **kwargs: RealOpenAI(
        **dict(kwargs, max_retries=0),
        http_client=httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(code, json={'error': {'message': 'secret-server-body'}})))))
    with pytest.raises(RuntimeError) as err:
        ai.ask_ai('test', 'test')
    assert fragment in str(err.value)
    assert 'secret-server-body' not in str(err.value)


def test_no_key_no_network(monkeypatch):
    monkeypatch.setattr(ai, 'config', lambda: {'key': ''})
    with pytest.raises(RuntimeError, match='服务尚未就绪'):
        ai.ask_ai('test', 'test')


@pytest.mark.parametrize('content,finish', [('', 'stop'), ('   ', 'stop'), ('partial', 'length')])
def test_incomplete_output_is_never_success(monkeypatch, content, finish):
    monkeypatch.setattr(ai, 'config', lambda: {'key': 'test-key', 'base_url': 'https://api.deepseek.com',
                                              'model': 'deepseek-flash', 'vision_model': 'deepseek-flash'})
    def respond(request):
        return httpx.Response(200, json={
            'id': 'test', 'object': 'chat.completion', 'created': 0, 'model': 'deepseek-flash',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': content}, 'finish_reason': finish}],
        })
    monkeypatch.setattr(ai, 'OpenAI', lambda **kwargs: RealOpenAI(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond))))
    with pytest.raises(ValueError):
        ai.ask_ai('test', 'test')

