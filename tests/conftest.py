"""All automated checks are offline and isolated from actual secret stores."""
import pytest
from core import ai, settings, classroom, collaboration
from core.limits import UsageLimiter


@pytest.fixture(autouse=True)
def isolate_service_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'secret_value', lambda name: None)
    monkeypatch.setattr(ai, 'secret_value', lambda name: None)
    monkeypatch.setattr(ai, 'LIMITER', UsageLimiter())
    monkeypatch.setattr(collaboration, 'CREATION_LIMITER', UsageLimiter())
    monkeypatch.setattr(classroom, 'DATA_DIR', tmp_path / 'classroom')
