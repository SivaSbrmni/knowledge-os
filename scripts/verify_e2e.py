#!/usr/bin/env python3
"""
End-to-end verification script for Knowledge OS (Phases 0–2).
Run after: alembic upgrade head && ensure_platform_workspace.py
"""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from knowledge_os.api.app import app
from knowledge_os.domain.enums import Role


async def run() -> int:
    errors: list[str] = []
    passed: list[str] = []
    suffix = uuid4().hex[:8]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://verify") as client:
        # Health
        h = await client.get("/health")
        if h.status_code == 200 and h.json()["status"] == "healthy":
            passed.append("health")
        else:
            errors.append(f"health failed: {h.status_code}")

        r = await client.get("/ready")
        ready = r.json()
        if r.status_code == 200 and ready["database"] == "connected" and ready["redis"] == "connected":
            passed.append("ready (db+redis)")
        else:
            errors.append(f"ready failed: {ready}")

        admin_id = str(uuid4())
        token_resp = await client.post(
            "/api/v1/auth/dev-token",
            json={
                "user_id": admin_id,
                "email": f"admin-{suffix}@verify.example",
                "roles": [
                    Role.PLATFORM_ADMIN.value,
                    Role.ORG_ADMIN.value,
                    Role.WORKSPACE_ADMIN.value,
                    Role.MENTOR.value,
                ],
            },
        )
        if token_resp.status_code != 200:
            errors.append(f"dev-token failed: {token_resp.text}")
            print_report(passed, errors)
            return 1

        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        org = await client.post(
            "/api/v1/organizations",
            json={"name": f"Verify Org {suffix}", "slug": f"verify-org-{suffix}"},
            headers=headers,
        )
        if org.status_code != 201:
            errors.append(f"create org: {org.text}")
            print_report(passed, errors)
            return 1
        org_id = org.json()["id"]
        passed.append("create organization")

        ws = await client.post(
            f"/api/v1/organizations/{org_id}/workspaces",
            json={"name": "Verify WS", "slug": f"verify-ws-{suffix}"},
            headers=headers,
        )
        if ws.status_code != 201:
            errors.append(f"create workspace: {ws.text}")
            print_report(passed, errors)
            return 1
        workspace_id = ws.json()["id"]
        passed.append("create workspace")

        agent_path = Path(__file__).resolve().parents[1] / "examples" / "upsc-mentor-agent.json"
        agent_config = json.loads(agent_path.read_text())
        agent_config["tenant_id"] = org_id
        agent_config["workspace_id"] = workspace_id

        agent = await client.post(
            f"/api/v1/workspaces/{workspace_id}/agents",
            json={"config": agent_config, "activate": True},
            headers=headers,
        )
        if agent.status_code != 201:
            errors.append(f"register agent: {agent.text}")
            print_report(passed, errors)
            return 1
        passed.append("register agent v2.1")

        content = (
            "[Page 1]\nThe President of India is elected by an electoral college.\n\n"
            "[Page 2]\nArticle 54 defines the electoral college composition."
        ).encode()

        upload = await client.post(
            f"/api/v1/workspaces/{workspace_id}/knowledge/upload",
            headers=headers,
            files={"file": ("verify-doc.txt", content, "text/plain")},
            data={"agent_id": "upsc-mentor-v1", "chunk_strategy": "structure_aware"},
        )
        if upload.status_code != 201:
            errors.append(f"upload: {upload.text}")
            print_report(passed, errors)
            return 1
        asset = upload.json()
        if asset["status"] != "ready":
            errors.append(f"asset not ready: {asset['status']}")
        else:
            passed.append("upload + ingest")
        asset_id = asset["id"]

        upload2 = await client.post(
            f"/api/v1/workspaces/{workspace_id}/knowledge/upload",
            headers=headers,
            files={"file": ("verify-doc.txt", content, "text/plain")},
            data={"agent_id": "upsc-mentor-v1"},
        )
        if upload2.status_code == 201 and upload2.json()["id"] == asset_id:
            passed.append("idempotent re-upload")
        else:
            errors.append("idempotent re-upload failed")

        graph = await client.get(
            f"/api/v1/workspaces/{workspace_id}/knowledge/assets/{asset_id}/graph",
            headers=headers,
        )
        if graph.status_code == 200 and any(e["edge_type"] == "cites" for e in graph.json()):
            passed.append("knowledge graph cites edges")
        else:
            errors.append(f"graph edges: {graph.text}")

        artifacts = await client.get(
            f"/api/v1/workspaces/{workspace_id}/knowledge/assets/{asset_id}/artifacts",
            headers=headers,
        )
        if artifacts.status_code == 200 and len(artifacts.json()) > 0:
            passed.append("derived artifact (summary)")
        else:
            errors.append("derived artifacts missing")

        platform_upload = await client.post(
            "/api/v1/platform/knowledge/upload",
            headers=headers,
            files={"file": ("platform-sample.txt", b"Article 14 equality before law.", "text/plain")},
        )
        if platform_upload.status_code == 201 and platform_upload.json()["layer"] == "platform_public":
            passed.append("platform public upload")
        else:
            errors.append(f"platform upload: {platform_upload.text}")

        session = await client.post(
            f"/api/v1/workspaces/{workspace_id}/sessions",
            json={"agent_id": "upsc-mentor-v1"},
            headers=headers,
        )
        if session.status_code != 201:
            errors.append(f"create session: {session.text}")
            print_report(passed, errors)
            return 1
        session_id = session.json()["session_id"]
        passed.append("create session")

        query = await client.post(
            f"/api/v1/workspaces/{workspace_id}/sessions/{session_id}/query",
            json={"question": "How is the President elected?"},
            headers=headers,
        )
        if query.status_code != 200:
            errors.append(f"query: {query.text}")
        else:
            result = query.json()
            if not result["withheld"] and len(result["citations"]) >= 1:
                passed.append("query with citations + trust")
            else:
                errors.append(f"query withheld or no citations: {result}")

    print_report(passed, errors)
    return 0 if not errors else 1


def print_report(passed: list[str], errors: list[str]) -> None:
    print("\n=== Knowledge OS Verification ===\n")
    for p in passed:
        print(f"  PASS  {p}")
    for e in errors:
        print(f"  FAIL  {e}")
    print(f"\n{len(passed)} passed, {len(errors)} failed\n")


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
