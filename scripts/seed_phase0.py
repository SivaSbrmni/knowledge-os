#!/usr/bin/env python3
"""Seed Phase 0 demo data: org, workspace, user, UPSC agent."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from knowledge_os.adapters.messaging.event_bus import InMemoryEventBus
from knowledge_os.adapters.persistence.database import get_session_factory
from knowledge_os.adapters.persistence.repositories import (
    PostgresAgentRepository,
    PostgresAuditStore,
    PostgresTenantRepository,
)
from knowledge_os.domain.enums import Role
from knowledge_os.schemas.agent_validator import AgentSchemaValidator
from knowledge_os.services.platform import AgentRegistryService, TenantService


async def main() -> None:
    factory = get_session_factory()
    event_bus = InMemoryEventBus()

    async with factory() as session:
        tenant_repo = PostgresTenantRepository(session)
        audit_store = PostgresAuditStore(session)
        tenant_service = TenantService(tenant_repo, audit_store, event_bus)
        agent_service = AgentRegistryService(
            PostgresAgentRepository(session),
            tenant_repo,
            audit_store,
            event_bus,
            AgentSchemaValidator(),
        )

        org = await tenant_service.create_organization("UPSC Academy", "upsc-academy")
        workspace = await tenant_service.create_workspace(org.id, "UPSC 2026", "upsc-2026")
        admin_id = uuid4()
        admin = await tenant_service.register_user("admin@upsc-academy.example", "Platform Admin")
        await tenant_service.add_workspace_member(
            workspace.id, admin.id, Role.WORKSPACE_ADMIN.value
        )

        agent_path = Path(__file__).resolve().parents[1] / "examples" / "upsc-mentor-agent.json"
        config = json.loads(agent_path.read_text())
        config["tenant_id"] = str(org.id)
        config["workspace_id"] = str(workspace.id)

        agent = await agent_service.register_agent(config, actor_id=admin.id, activate=True)
        await session.commit()

        print("Phase 0 seed complete:")
        print(f"  Organization: {org.id} ({org.slug})")
        print(f"  Workspace:    {workspace.id} ({workspace.slug})")
        print(f"  Admin User:   {admin.id} ({admin.email})")
        print(f"  Agent:        {agent.agent_id} v{agent.version} (active={agent.is_active})")
        print(f"  Events:       {len(event_bus.published)} published")


if __name__ == "__main__":
    asyncio.run(main())
