"""视觉 provider 切换的离线测试：默认 DeepSeek、可切 DashScope、缺 Key 明确报错。"""
import pytest

from core import ai


def test_default_vision_provider_is_deepseek(monkeypatch):
    monkeypatch.delenv('VISION_PROVIDER', raising=False)
    cfg = ai.vision_config()
    assert cfg['provider'] == 'deepseek'


def test_switch_to_dashscope_qwen(monkeypatch):
    monkeypatch.setenv('VISION_PROVIDER', 'dashscope')
    monkeypatch.setenv('DASHSCOPE_API_KEY', 'sk-test')
    cfg = ai.vision_config()
    assert cfg['provider'] == 'dashscope'
    assert cfg['model'] == 'qwen3.8-flash'
    assert cfg['base_url'].endswith('/compatible-mode/v1')


def test_dashscope_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.setenv('VISION_PROVIDER', 'dashscope')
    monkeypatch.delenv('DASHSCOPE_API_KEY', raising=False)
    messages = [{'role': 'user', 'content': [
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AA==', 'detail': 'original'}},
    ]}]
    with pytest.raises(RuntimeError) as exc:
        ai.completion(messages, vision=True, max_tokens=100)
    assert 'DASHSCOPE_API_KEY' in str(exc.value)


def test_strip_image_detail_removes_detail_field():
    messages = [{'role': 'user', 'content': [
        {'type': 'text', 'text': 'hi'},
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,AA==', 'detail': 'original'}},
    ]}]
    cleaned = ai._strip_image_detail(messages)
    image = cleaned[0]['content'][1]['image_url']
    assert 'detail' not in image
    assert image['url'].startswith('data:image/png;base64,')
