"""Authorization enforcement tests — IDOR and session binding."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from knowledge_os.api.app import app
from knowledge_os.domain.enums import Role


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _dev_token(client: AsyncClient, user_id: str, roles: list[str]) -> dict:
    resp = await client.post(
        "/api/v1/auth/dev-token",
        json={
            "user_id": user_id,
            "email": f"user-{user_id[:8]}@test.example",
            "roles": roles,
        },
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_workspace_idor_denied_without_membership(client: AsyncClient):
    """User with JWT roles but no DB membership cannot access workspace in testing env."""
    suffix = uuid.uuid4().hex[:8]
    admin_id = str(uuid.uuid4())
    admin_headers = await _dev_token(
        client,
        admin_id,
        [Role.PLATFORM_ADMIN.value, Role.WORKSPACE_ADMIN.value, Role.MENTOR.value],
    )

    org_resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Auth Test Org", "slug": f"auth-org-{suffix}"},
        headers=admin_headers,
    )
    workspace_id = (
        await client.post(
            f"/api/v1/organizations/{org_resp.json()['id']}/workspaces",
            json={"name": "Auth WS", "slug": f"auth-ws-{suffix}"},
            headers=admin_headers,
        )
    ).json()["id"]

    stranger_id = str(uuid.uuid4())
    stranger_headers = await _dev_token(client, stranger_id, [])

    assets_resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/knowledge/assets",
        headers=stranger_headers,
    )
    assert assets_resp.status_code == 403


@pytest.mark.asyncio
async def test_session_bound_to_creator(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    owner_id = str(uuid.uuid4())
    owner_headers = await _dev_token(
        client,
        owner_id,
        [Role.PLATFORM_ADMIN.value, Role.WORKSPACE_ADMIN.value, Role.MENTOR.value],
    )

    org_resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Session Org", "slug": f"session-org-{suffix}"},
        headers=owner_headers,
    )
    workspace_id = (
        await client.post(
            f"/api/v1/organizations/{org_resp.json()['id']}/workspaces",
            json={"name": "Session WS", "slug": f"session-ws-{suffix}"},
            headers=owner_headers,
        )
    ).json()["id"]

    agent_config_path = __import__("pathlib").Path(__file__).parent.parent / "examples" / "upsc-mentor-agent.json"
    agent_config = __import__("json").loads(agent_config_path.read_text())
    agent_config["tenant_id"] = org_resp.json()["id"]
    agent_config["workspace_id"] = workspace_id

    await client.post(
        f"/api/v1/workspaces/{workspace_id}/agents",
        json={"config": agent_config, "activate": True},
        headers=owner_headers,
    )

    session_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/sessions",
        json={"agent_id": "upsc-mentor-v1"},
        headers=owner_headers,
    )
    session_id = session_resp.json()["session_id"]

    other_id = str(uuid.uuid4())
    other_headers = await _dev_token(
        client,
        other_id,
        [Role.PLATFORM_ADMIN.value, Role.MENTOR.value],
    )

    query_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/sessions/{session_id}/query",
        json={"question": "Test question"},
        headers=other_headers,
    )
    assert query_resp.status_code == 403


@pytest.mark.asyncio
async def test_platform_admin_can_access_workspace_in_dev(client: AsyncClient):
    """Platform admin JWT bypass works in non-production for operations."""
    suffix = uuid.uuid4().hex[:8]
    admin_id = str(uuid.uuid4())
    admin_headers = await _dev_token(
        client,
        admin_id,
        [Role.PLATFORM_ADMIN.value, Role.WORKSPACE_ADMIN.value, Role.MENTOR.value],
    )

    org_resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Admin Org", "slug": f"admin-org-{suffix}"},
        headers=admin_headers,
    )
    workspace_id = (
        await client.post(
            f"/api/v1/organizations/{org_resp.json()['id']}/workspaces",
            json={"name": "Admin WS", "slug": f"admin-ws-{suffix}"},
            headers=admin_headers,
        )
    ).json()["id"]

    assets_resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/knowledge/assets",
        headers=admin_headers,
    )
    assert assets_resp.status_code == 200
