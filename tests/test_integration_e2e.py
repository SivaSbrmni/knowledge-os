"""End-to-end integration tests against real Postgres + Redis."""

import json
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from knowledge_os.api.app import app
from knowledge_os.domain.enums import Role


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_and_ready(client: AsyncClient):
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    ready = await client.get("/ready")
    assert ready.status_code == 200
    data = ready.json()
    assert data["database"] == "connected"
    assert data["redis"] == "connected"


@pytest.mark.asyncio
async def test_full_platform_flow(client: AsyncClient):
    suffix = uuid.uuid4().hex[:8]
    admin_id = str(uuid.uuid4())
    token_resp = await client.post(
        "/api/v1/auth/dev-token",
        json={
            "user_id": admin_id,
            "email": f"admin-{suffix}@test.example",
            "roles": [Role.PLATFORM_ADMIN.value, Role.WORKSPACE_ADMIN.value, Role.MENTOR.value],
        },
    )
    assert token_resp.status_code == 200
    headers = {"Authorization": f"Bearer {token_resp.json()['access_token']}"}

    org_resp = await client.post(
        "/api/v1/organizations",
        json={"name": "Test Academy", "slug": f"test-academy-{suffix}"},
        headers=headers,
    )
    assert org_resp.status_code == 201
    org_id = org_resp.json()["id"]

    ws_resp = await client.post(
        f"/api/v1/organizations/{org_id}/workspaces",
        json={"name": "Test WS", "slug": f"test-ws-{suffix}"},
        headers=headers,
    )
    assert ws_resp.status_code == 201
    workspace_id = ws_resp.json()["id"]

    agent_config = json.loads(
        (Path(__file__).parent.parent / "examples" / "upsc-mentor-agent.json").read_text()
    )
    agent_config["tenant_id"] = org_id
    agent_config["workspace_id"] = workspace_id
    agent_config.setdefault("reasoning_policy", {})["min_evidence_packets"] = 1

    agent_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/agents",
        json={"config": agent_config, "activate": True},
        headers=headers,
    )
    assert agent_resp.status_code == 201

    content = (
        "[Page 1]\nThe President of India is elected by an electoral college.\n\n"
        "[Page 2]\nArticle 54 defines the electoral college composition."
    ).encode()
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/knowledge/upload",
        headers=headers,
        files={"file": ("constitution.txt", content, "text/plain")},
        data={"agent_id": "upsc-mentor-v1", "chunk_strategy": "structure_aware"},
    )
    assert upload_resp.status_code == 201
    asset_id = upload_resp.json()["id"]

    session_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/sessions",
        json={"agent_id": "upsc-mentor-v1"},
        headers=headers,
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["session_id"]

    query_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/sessions/{session_id}/query",
        json={"question": "How is the President of India elected?"},
        headers=headers,
    )
    assert query_resp.status_code == 200
    result = query_resp.json()
    assert result["withheld"] is False
    assert len(result["citations"]) >= 1
