from uuid import uuid4

import pytest

from knowledge_os.adapters.auth.jwt_provider import JWTAuthProvider
from knowledge_os.config import get_settings


@pytest.fixture
def auth_provider() -> JWTAuthProvider:
    return JWTAuthProvider()


@pytest.mark.asyncio
async def test_issue_and_verify_dev_token(auth_provider: JWTAuthProvider, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    get_settings.cache_clear()
    auth_provider = JWTAuthProvider()

    user_id = uuid4()
    token = await auth_provider.issue_dev_token(user_id, "test@example.com", ["workspace_admin"])
    claims = await auth_provider.verify_token(token)

    assert claims["sub"] == str(user_id)
    assert claims["email"] == "test@example.com"
    assert "workspace_admin" in claims["roles"]


@pytest.mark.asyncio
async def test_invalid_token_raises(auth_provider: JWTAuthProvider):
    with pytest.raises(ValueError, match="Invalid or expired token"):
        await auth_provider.verify_token("not-a-valid-token")
