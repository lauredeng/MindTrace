"""Offline tests: real dependencies, explicit fixture responses, no external API."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch, tmp_path):
    monkeypatch.setenv('MINDTRACE_ENV', 'production')
    monkeypatch.setenv('MINDTRACE_ENABLE_DEVELOPER_MODE', '0')
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    for name in ('MINDTRACE_DATABASE','MINDTRACE_BACKEND_URL','MINDTRACE_HEADLESS','MINDTRACE_BACKGROUND'):
        monkeypatch.delenv(name,raising=False)
    from core import ai, settings, storage

    def forbidden(*args, **kwargs):
        raise AssertionError('External model calls are forbidden in offline tests')

    monkeypatch.setattr(ai, 'OpenAI', forbidden)
    monkeypatch.setattr(ai, 'secret_value', lambda name: None)
    monkeypatch.setattr(settings, 'secret_value', lambda name: None)
    monkeypatch.setattr(storage, 'DATA_DIR', tmp_path)
    from core import classroom, collaboration
    from core.limits import UsageLimiter
    monkeypatch.setattr(classroom, 'DATA_DIR', tmp_path / 'classroom')
    monkeypatch.setattr(ai, 'LIMITER', UsageLimiter())
    monkeypatch.setattr(collaboration, 'CREATION_LIMITER', UsageLimiter())
