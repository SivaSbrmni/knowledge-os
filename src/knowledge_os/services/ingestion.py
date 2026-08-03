import hashlib
from pathlib import Path
from uuid import UUID

import structlog

from knowledge_os.adapters.ingestion.chunker import chunk_fixed
from knowledge_os.adapters.ingestion.embedder import dev_embed
from knowledge_os.adapters.ingestion.extractor import extract_text_from_bytes
from knowledge_os.adapters.messaging.event_bus import build_platform_event
from knowledge_os.domain.enums import EventTopic
from knowledge_os.domain.utils import new_trace_id
from knowledge_os.ports.knowledge import KnowledgeRepository, VectorStore
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.ports.repositories import EventBus
from knowledge_os.schemas.llm_policy import parse_llm_policy

logger = structlog.get_logger()


class IngestionService:
    """Upload → extract → chunk → embed → index. Emits knowledge.* events."""

    def __init__(
        self,
        knowledge_repo: KnowledgeRepository,
        vector_store: VectorStore,
        llm_gateway: LLMGateway | None,
        event_bus: EventBus,
        storage_root: Path,
        use_dev_embeddings: bool = False,
    ):
        self._knowledge_repo = knowledge_repo
        self._vector_store = vector_store
        self._llm_gateway = llm_gateway
        self._event_bus = event_bus
        self._storage_root = storage_root
        self._use_dev_embeddings = use_dev_embeddings
        self._storage_root.mkdir(parents=True, exist_ok=True)

    async def ingest_upload(
        self,
        workspace_id: UUID,
        filename: str,
        content: bytes,
        mime_type: str,
        agent_config: dict | None = None,
        *,
        trace_id: str | None = None,
        actor_id: UUID | None = None,
    ):
        trace_id = trace_id or new_trace_id()
        content_hash = hashlib.sha256(content).hexdigest()

        asset = await self._knowledge_repo.create_asset(
            workspace_id=workspace_id,
            filename=filename,
            content_hash=content_hash,
            storage_path="",
            mime_type=mime_type,
            page_count=None,
            status="processing",
        )

        storage_dir = self._storage_root / str(workspace_id)
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_path = storage_dir / f"{asset.id}_{filename}"
        storage_path.write_bytes(content)

        await self._emit(
            trace_id, workspace_id, actor_id, "knowledge.upload.received",
            {"asset_id": str(asset.id), "filename": filename},
        )

        try:
            text, page_count = extract_text_from_bytes(content, mime_type, filename)
            chunks = chunk_fixed(text)
            model_id = "dev-embed"

            if agent_config and agent_config.get("schema_version") == "2.1":
                policy = parse_llm_policy(agent_config)
                model_id = policy.embedding.model.model_id

            for tc in chunks:
                chunk = await self._knowledge_repo.create_chunk(
                    asset_id=asset.id,
                    workspace_id=workspace_id,
                    chunk_index=tc.chunk_index,
                    text=tc.text,
                    page=tc.page,
                    section=tc.section,
                    token_count=tc.token_count,
                )
                embedding = await self._embed_text(tc.text, workspace_id, agent_config)
                await self._vector_store.upsert(
                    chunk_id=chunk.id,
                    workspace_id=workspace_id,
                    embedding=embedding,
                    model_id=model_id,
                )

            asset = await self._knowledge_repo.update_asset_status(asset.id, "ready")
            await self._emit(
                trace_id, workspace_id, actor_id, "knowledge.index.completed",
                {"asset_id": str(asset.id), "chunk_count": len(chunks), "page_count": page_count},
            )
            return asset

        except Exception as exc:
            logger.error("ingestion_failed", asset_id=str(asset.id), error=str(exc))
            await self._knowledge_repo.update_asset_status(asset.id, "failed")
            raise

    async def _embed_text(
        self, text: str, workspace_id: UUID, agent_config: dict | None
    ) -> list[float]:
        if self._use_dev_embeddings or self._llm_gateway is None:
            return dev_embed(text)

        if agent_config and agent_config.get("schema_version") == "2.1":
            from knowledge_os.domain.llm import EmbeddingRequest
            from knowledge_os.schemas.llm_policy import parse_llm_policy

            policy = parse_llm_policy(agent_config)
            try:
                response = await self._llm_gateway.embed(
                    policy,
                    workspace_id,
                    EmbeddingRequest(texts=[text], model_id=policy.embedding.model.model_id),
                )
                return response.embeddings[0]
            except Exception as exc:
                logger.warning("llm_embed_fallback_dev", error=str(exc))

        return dev_embed(text)

    async def _emit(
        self, trace_id: str, workspace_id: UUID, actor_id: UUID | None, event_type: str, payload: dict
    ):
        event = build_platform_event(
            topic=EventTopic.KNOWLEDGE,
            event_type=event_type,
            trace_id=trace_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            payload=payload,
        )
        await self._event_bus.publish(event)

    async def list_assets(self, workspace_id: UUID):
        return await self._knowledge_repo.list_assets(workspace_id)
