#!/usr/bin/env python3
"""Ensure platform-public workspace exists for FK constraints."""

import asyncio
from uuid import UUID

from sqlalchemy import select

from knowledge_os.adapters.persistence.database import get_session_factory
from knowledge_os.adapters.persistence.models import OrganizationModel, WorkspaceModel
from knowledge_os.config import get_settings, PLATFORM_WORKSPACE_ID


async def main() -> None:
    settings = get_settings()
    platform_ws_id = UUID(settings.platform_workspace_id)
    factory = get_session_factory()

    async with factory() as session:
        existing = await session.get(WorkspaceModel, platform_ws_id)
        if existing:
            print(f"Platform workspace exists: {platform_ws_id}")
            return

        org_id = UUID("00000000-0000-0000-0000-000000000001")
        org = await session.get(OrganizationModel, org_id)
        if org is None:
            org = OrganizationModel(
                id=org_id,
                name="Knowledge OS Platform",
                slug="knowledge-os-platform",
                is_active=True,
            )
            session.add(org)
            await session.flush()

        workspace = WorkspaceModel(
            id=platform_ws_id,
            organization_id=org_id,
            name="Platform Public Knowledge",
            slug="platform-public",
            is_active=True,
        )
        session.add(workspace)
        await session.commit()
        print(f"Created platform workspace: {platform_ws_id}")


if __name__ == "__main__":
    asyncio.run(main())
