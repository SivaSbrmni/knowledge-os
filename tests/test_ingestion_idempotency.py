import hashlib
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from knowledge_os.services.ingestion import IngestionService


@pytest.mark.asyncio
async def test_idempotent_ingestion_returns_existing_asset(tmp_path):
    workspace_id = uuid4()
    content = b"same content for idempotency test"
    content_hash = hashlib.sha256(content).hexdigest()

    existing_asset = MagicMock()
    existing_asset.id = uuid4()
    existing_asset.content_hash = content_hash

    knowledge_repo = AsyncMock()
    knowledge_repo.find_asset_by_hash.return_value = existing_asset

    service = IngestionService(
        knowledge_repo=knowledge_repo,
        vector_store=AsyncMock(),
        graph_repo=AsyncMock(),
        run_repo=AsyncMock(),
        artifact_repo=AsyncMock(),
        llm_gateway=None,
        event_bus=AsyncMock(),
        storage_root=tmp_path,
        pipeline_version="2.0",
        use_dev_embeddings=True,
    )

    result = await service.ingest_upload(
        workspace_id=workspace_id,
        filename="test.txt",
        content=content,
        mime_type="text/plain",
    )

    assert result == existing_asset
    knowledge_repo.create_asset.assert_not_called()
