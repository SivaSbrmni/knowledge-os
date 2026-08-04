
import pytest


@pytest.fixture(autouse=True)
def _test_environment(monkeypatch, request):
    if "integration_e2e" in request.node.nodeid or "test_authorization" in request.node.nodeid:
        monkeypatch.setenv("ENVIRONMENT", "development")
    else:
        monkeypatch.setenv("ENVIRONMENT", "testing")
    get_settings.cache_clear()
    from knowledge_os.api.dependencies import reset_event_bus_cache

    reset_event_bus_cache()


from knowledge_os.config import get_settings  # noqa: E402
