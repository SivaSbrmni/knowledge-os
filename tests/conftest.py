
import pytest


@pytest.fixture(autouse=True)
def _test_environment(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "testing")
    get_settings.cache_clear()


from knowledge_os.config import get_settings  # noqa: E402
