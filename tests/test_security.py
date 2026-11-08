from pathlib import Path
import sys
import zipfile
import pytest
from core import ai

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from export_source import export_source


def test_cloud_value_wins_without_copying(monkeypatch):
    monkeypatch.setattr(ai, 'dotenv_values', lambda *a, **kw: {'DEEPSEEK_API_KEY': 'local-fixture'})
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'cloud-fixture')
    assert ai.config()['key'] == 'cloud-fixture'


def test_empty_dotenv_does_not_mask_cloud(monkeypatch):
    monkeypatch.setattr(ai, 'dotenv_values', lambda *a, **kw: {'DEEPSEEK_API_KEY': ''})
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'proxy-placeholder-fixture')
    assert ai.config()['key'] == 'proxy-placeholder-fixture'


def test_local_fallback_does_not_mutate_environment(monkeypatch):
    monkeypatch.setenv('MINDTRACE_ENV', 'development')
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    monkeypatch.setattr(ai, 'dotenv_values', lambda *a, **kw: {'DEEPSEEK_API_KEY': 'local-fixture'})
    assert ai.config()['key'] == 'local-fixture'
    import os
    assert 'DEEPSEEK_API_KEY' not in os.environ


def test_export_never_reads_credential_or_runtime_files(tmp_path, monkeypatch):
    (tmp_path / 'app.py').write_text('# source only', encoding='utf-8')
    for name in ('.env', '.env.local', 'debug.log'):
        (tmp_path / name).write_text('EXCLUDED_FIXTURE', encoding='utf-8')
    original = Path.read_bytes
    def guarded(path):
        if path.name in ('.env', '.env.local', 'debug.log'):
            raise AssertionError('Exporter must not even open excluded files')
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', guarded)
    output = export_source(tmp_path)
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {'mindtrace_mvp/app.py', 'mindtrace_mvp/.env.example'}
        assert archive.read('mindtrace_mvp/.env.example').splitlines()[0] == b'DEEPSEEK_API_KEY='
    with pytest.raises(FileExistsError):
        export_source(tmp_path)


def test_export_refuses_hardcoded_token_fixture(tmp_path):
    synthetic = 'sk-' + 'TESTONLY' * 4
    (tmp_path / 'app.py').write_text('# ' + synthetic, encoding='utf-8')
    with pytest.raises(ValueError, match='credential detected'):
        export_source(tmp_path)
    assert not (tmp_path / 'exports').exists()


def test_explicit_visitor_key_never_reads_owner_settings(monkeypatch):
    import httpx
    from openai import OpenAI as RealOpenAI
    requests = []
    def forbidden():
        raise AssertionError('Must not consult owner credentials for visitor requests')
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            'id': 'fixture', 'object': 'chat.completion', 'created': 0, 'model': 'deepseek-flash',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'ok'}, 'finish_reason': 'stop'}],
        })
    monkeypatch.setattr(ai, 'config', forbidden)
    monkeypatch.setattr(ai, 'OpenAI', lambda **kwargs: RealOpenAI(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond))))
    for visitor in ('VISITOR-A-FIXTURE', 'VISITOR-B-FIXTURE'):
        assert ai.ask_ai('test', 'test', api_key=visitor) == 'ok'
        assert requests[-1].headers['authorization'] == 'Bearer ' + visitor
        assert requests[-1].url.host == 'api.deepseek.com'
    with pytest.raises(RuntimeError, match='服务尚未就绪'):
        ai.ask_ai('test', 'test', api_key='')


def test_server_config_env_then_secrets_without_dotenv(monkeypatch):
    environment = {'DEEPSEEK_API_KEY': 'ENVIRONMENT-FIXTURE'}
    secrets = {'DEEPSEEK_API_KEY': 'SECRETS-FIXTURE', 'DEEPSEEK_MODEL': 'model-from-secrets'}
    monkeypatch.setattr(ai.os, 'getenv', lambda name, default=None: environment.get(name, default))
    monkeypatch.setattr(ai, 'secret_value', lambda name: secrets.get(name))
    monkeypatch.setattr(ai, 'development_mode', lambda: False)
    def forbidden(*args, **kwargs):
        raise AssertionError('Production must not open dotenv')
    monkeypatch.setattr(ai, 'dotenv_values', forbidden)
    assert ai.config()['key'] == 'ENVIRONMENT-FIXTURE'
    assert ai.config()['model'] == 'model-from-secrets'
    environment.clear()
    assert ai.config()['key'] == 'SECRETS-FIXTURE'
    secrets.clear()
    assert ai.config()['key'] == ''


def test_upstream_credential_echo_is_redacted(monkeypatch):
    import httpx
    from openai import OpenAI as RealOpenAI
    key = 'SYNTHETIC-SECRET-ECHO'
    def respond(request):
        return httpx.Response(200, json={
            'id': 'fixture', 'object': 'chat.completion', 'created': 0, 'model': 'deepseek-flash',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'echo ' + key}, 'finish_reason': 'stop'}],
        })
    captured = []
    def client(**kwargs):
        captured.append(kwargs['max_retries'])
        return RealOpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(ai, 'OpenAI', client)
    reply = ai.ask_ai('test', 'test', api_key=key)
    assert key not in reply and '凭据已隐藏' in reply
    assert captured == [0]
