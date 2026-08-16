#!/usr/bin/env python3
"""Import sample text into platform-public knowledge layer."""

import asyncio
from pathlib import Path
from uuid import UUID

from knowledge_os.adapters.messaging.event_bus import InMemoryEventBus
from knowledge_os.adapters.persistence.database import get_session_factory
from knowledge_os.adapters.persistence.knowledge_repositories import (
    PostgresDerivedArtifactRepository,
    PostgresIngestionRunRepository,
    PostgresKnowledgeGraphRepository,
    PostgresKnowledgeRepository,
    PostgresVectorStore,
)
from knowledge_os.config import get_settings
from knowledge_os.services.ingestion import IngestionService

SAMPLE = """
[Page 1]
The Constitution of India is the supreme law of India.

[Page 2]
Article 14 guarantees equality before the law and equal protection of laws within India.
Article 21 protects the right to life and personal liberty.
"""


async def main() -> None:
    settings = get_settings()
    factory = get_session_factory()
    event_bus = InMemoryEventBus()

    async with factory() as session:
        ingestion = IngestionService(
            knowledge_repo=PostgresKnowledgeRepository(session),
            vector_store=PostgresVectorStore(session),
            graph_repo=PostgresKnowledgeGraphRepository(session),
            run_repo=PostgresIngestionRunRepository(session),
            artifact_repo=PostgresDerivedArtifactRepository(session),
            llm_gateway=None,
            event_bus=event_bus,
            storage_root=settings.storage_path,
            pipeline_version=settings.pipeline_version,
            use_dev_embeddings=True,
        )
        platform_ws = UUID(settings.platform_workspace_id)
        asset = await ingestion.ingest_platform_public(
            platform_workspace_id=platform_ws,
            filename="constitution-sample.txt",
            content=SAMPLE.encode(),
            mime_type="text/plain",
        )
        await session.commit()
        print(f"Platform public asset ready: {asset.id} ({asset.layer})")
        print(f"Events published: {len(event_bus.published)}")


if __name__ == "__main__":
    asyncio.run(main())
