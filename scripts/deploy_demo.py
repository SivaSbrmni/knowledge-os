#!/usr/bin/env python3
"""Bootstrap demo data and print credentials for manual testing."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from knowledge_os.adapters.auth.jwt_provider import JWTAuthProvider
from knowledge_os.adapters.messaging.event_bus import InMemoryEventBus
from knowledge_os.adapters.persistence.database import get_session_factory
from knowledge_os.adapters.persistence.models import UserModel, WorkspaceModel
from knowledge_os.adapters.persistence.repositories import (
    PostgresAgentRepository,
    PostgresAuditStore,
    PostgresTenantRepository,
)
from knowledge_os.domain.enums import Role
from knowledge_os.schemas.agent_validator import AgentSchemaValidator
from knowledge_os.services.platform import AgentRegistryService, TenantService


async def main() -> int:
    factory = get_session_factory()
    event_bus = InMemoryEventBus()
    auth = JWTAuthProvider()

    async with factory() as session:
        tenant_repo = PostgresTenantRepository(session)
        org = await tenant_repo.get_organization_by_slug("demo-academy")
        if org is None:
            tenant_service = TenantService(tenant_repo, PostgresAuditStore(session), event_bus)
            agent_service = AgentRegistryService(
                PostgresAgentRepository(session),
                tenant_repo,
                PostgresAuditStore(session),
                event_bus,
                AgentSchemaValidator(),
            )
            org = await tenant_service.create_organization("Demo Academy", "demo-academy")
            workspace = await tenant_service.create_workspace(org.id, "Demo Workspace", "demo-workspace")
            admin = await tenant_service.register_user("demo@knowledge-os.dev", "Demo Admin")
            await tenant_service.add_workspace_member(
                workspace.id, admin.id, Role.WORKSPACE_ADMIN.value
            )

            agent_path = Path(__file__).resolve().parents[1] / "examples" / "upsc-mentor-agent.json"
            config = json.loads(agent_path.read_text())
            config["tenant_id"] = str(org.id)
            config["workspace_id"] = str(workspace.id)
            await agent_service.register_agent(config, actor_id=admin.id, activate=True)
            await session.commit()
            user_id = admin.id
        else:
            workspace = (
                await session.scalars(
                    select(WorkspaceModel).where(WorkspaceModel.organization_id == org.id).limit(1)
                )
            ).first()
            if workspace is None:
                print("Organization exists but no workspace found", file=sys.stderr)
                return 1
            user = (
                await session.scalars(
                    select(UserModel).where(UserModel.email == "demo@knowledge-os.dev").limit(1)
                )
            ).first()
            user_id = user.id if user else uuid4()

        token = await auth.issue_dev_token(
            user_id,
            "demo@knowledge-os.dev",
            [
                Role.PLATFORM_ADMIN.value,
                Role.ORG_ADMIN.value,
                Role.WORKSPACE_ADMIN.value,
                Role.MENTOR.value,
            ],
        )

    print(json.dumps({
        "organization_id": str(org.id),
        "workspace_id": str(workspace.id),
        "agent_id": "upsc-mentor-v1",
        "access_token": token,
        "ui_path": "/ui",
        "docs_path": "/docs",
        "health_path": "/health",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
