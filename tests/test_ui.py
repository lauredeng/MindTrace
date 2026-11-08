from navigation_helpers import route,main_labels
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from core import storage, ai

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv('MINDTRACE_ENV', 'development')
    monkeypatch.setenv('MINDTRACE_SHARED_MODE', '0')
    monkeypatch.setenv('MINDTRACE_ENABLE_DEVELOPER_MODE', '0')
    # Isolated real JSON persistence, no writes into user records.
    target = tmp_path / 'runs.json'
    monkeypatch.setattr(storage.load_runs, '__defaults__', (target,))
    monkeypatch.setattr(storage.save_runs, '__defaults__', (target,))
    monkeypatch.setattr(storage.append_record, '__defaults__', (target,))
    monkeypatch.setattr(storage.save_review, '__defaults__', (target,))
    monkeypatch.setattr(storage, 'STUDENT_STORE', tmp_path / 'students.json')
    monkeypatch.setattr(ai, 'ai_ready', lambda: False)
    # Never open the real credential file or inspect real process credentials.
    monkeypatch.setattr(ai, 'config', lambda: {
        'key': '', 'base_url': 'https://api.deepseek.com',
        'model': 'deepseek-flash', 'vision_model': 'deepseek-flash'})
    at = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    assert not at.exception
    route(at,'教师批量分析')
    return at


def click_label(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception


def test_teacher_to_review_and_history(app):
    at = app
    assert at.session_state['experience_page'] == '教师批量分析'
    click_label(at, '载入 12 份匿名示例作业')
    assert at.metric[0].value == '12'
    assert at.metric[1].value == '6'
    assert len(storage.load_runs()) == 1
    at.run()
    assert len(storage.load_runs()) == 1
    route(at,'证据复核与统计')
    assert not at.exception
    click_label(at, '保存教师复核')
    assert '0' in storage.load_runs()[0]['reviews']
    route(at,'运行记录')
    assert not at.exception
    click_label(at, '恢复到当前工作区')


def test_student_practice_and_profile(app):
    at = app
    route(at,'学生辅导体验')
    assert not at.exception
    click_label(at, '建立诊断与追问')
    click_label(at, '保存本次辅导证据')
    click_label(at, '生成一道新变式')
    # Select the actual generated answer, exercise mathematics is independently checked.
    answer = at.session_state['exercise']['answer']
    next(t for t in at.text_input if t.label == '你的导数表达式').set_value(answer)
    click_label(at, '提交并验证')
    route(at,'学习认知画像')
    assert not at.exception
    assert at.metric[0].value == '2'
    assert at.metric[1].value == '1'


def test_no_demo_profile_without_opt_in(app):
    at = app
    click_label(at, '载入 12 份匿名示例作业')
    route(at,'学习认知画像')
    assert not at.exception
    assert not at.metric
    at.checkbox[0].check().run()
    assert not at.exception
    assert at.selectbox[0].options[0] == 'S01'


def test_image_draft_requires_confirmation(app):
    at = app
    # Explicit synthetic UI fixture, not an OCR accuracy test or a live API call.
    at.session_state['ocr_results'] = [{
        'transcription': 'synthetic transport fixture', 'warnings': [],
        'filename': 'test-only.png', 'image_sha256': 'fixture',
        'records': [{'student_id': 'T01', 'question': 'x**2', 'student_answer': '2*x'}],
    }]
    at.run()
    submit = next(b for b in at.button if b.label == '确认转写并进行数学验证')
    assert submit.disabled
    assert not storage.load_runs()
    next(c for c in at.checkbox if c.label == '我已对照原图，确认上表题目与学生答案。').check().run()
    click_label(at, '确认转写并进行数学验证')
    saved = storage.load_runs()
    assert saved[0]['source'] == '图片转写 · 教师已确认'
    assert saved[0]['results'][0]['status'] == 'correct'
    assert saved[0]['ocr_evidence'][0]['image_sha256'] == 'fixture'


def test_page_key_is_session_only_and_clearable(app, monkeypatch):
    at = app
    assert not any('API Key' in t.label for t in at.text_input)
    monkeypatch.setenv('MINDTRACE_ENABLE_DEVELOPER_MODE', '1')
    at.run()
    assert not any('API Key' in t.label for t in at.text_input)
    next(c for c in at.checkbox if c.label == '使用临时自带 Key').check().run()
    field = next(t for t in at.text_input if t.label == '开发者 DeepSeek API Key')
    assert field.proto.type == field.proto.PASSWORD
    field.set_value('SYNTHETIC-SESSION-CREDENTIAL').run()
    assert not at.exception
    assert not next(b for b in at.button if b.label == '检查 AI 连接').disabled
    click_label(at, '载入 12 份匿名示例作业')
    import json
    assert 'SYNTHETIC-SESSION-CREDENTIAL' not in json.dumps(storage.load_runs())
    click_label(at, '清除本次会话密钥')
    assert at.session_state['visitor_api_key'] == ''
    assert next(b for b in at.button if b.label == '检查 AI 连接').disabled


def test_product_mode_isolates_visitors_and_uses_server_ai(tmp_path, monkeypatch):
    monkeypatch.setenv('MINDTRACE_ENV', 'production')
    monkeypatch.setenv('MINDTRACE_ENABLE_DEVELOPER_MODE', '0')
    def forbidden(*args, **kwargs):
        raise AssertionError('Product mode must not read shared business files or expose server config')
    monkeypatch.setattr(ai, 'config', forbidden)
    monkeypatch.setattr(ai, 'ai_ready', lambda: True)
    calls = []
    def response(system, user, **kwargs):
        calls.append(kwargs)
        return '这是离线测试追问。你能分别求出内外层的导数吗？'
    monkeypatch.setattr(ai, 'ask_ai', response)
    monkeypatch.setattr(storage, 'load_runs', forbidden)
    monkeypatch.setattr(storage, 'append_record', forbidden)
    monkeypatch.setattr(storage, 'save_review', forbidden)
    first = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    second = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
    route(first,'教师批量分析')
    route(second,'教师批量分析')
    assert not first.exception and not second.exception
    first.session_state['visitor_api_key'] = 'UNENABLED-DEVELOPER-FIXTURE'
    first.run()
    assert not any('Key' in t.label for t in first.text_input)
    assert not any(e.label == '开发者设置' for e in first.expander)
    click_label(first, '载入 12 份匿名示例作业')
    assert first.metric[0].value == '12'
    assert second.metric[0].value == '—'
    route(first,'证据复核与统计')
    assert not first.exception
    click_label(first, '保存教师复核')
    route(second,'运行记录')
    assert not second.exception
    assert second.metric[0].value == '0'
    for visitor in (first, second):
        route(visitor,'学生辅导体验')
        click_label(visitor, '建立诊断与追问')
    assert calls[0]['api_key'] is None and calls[1]['api_key'] is None
    assert calls[0]['session_id'] != calls[1]['session_id']


def test_quota_exhaustion_preserves_math_and_user_flow(app, monkeypatch):
    from core.limits import UsageLimitError
    monkeypatch.setattr(ai, 'ai_ready', lambda: True)
    def limited(*args, **kwargs):
        raise UsageLimitError('今日 AI 体验额度已用完；数学验证仍可使用。')
    monkeypatch.setattr(ai, 'ask_ai', limited)
    route(app,'学生辅导体验')
    click_label(app, '建立诊断与追问')
    assert app.session_state['tutor_session']['evidence']['status'] == 'incorrect'
    assert any('额度' in error.value for error in app.error)
    click_label(app, '生成一道新变式')

