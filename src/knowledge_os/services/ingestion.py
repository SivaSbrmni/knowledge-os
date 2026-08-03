import hashlib
from pathlib import Path
from uuid import UUID

import structlog

from knowledge_os.adapters.ingestion.embedder import dev_embed
from knowledge_os.adapters.ingestion.extractor import extract_text_from_bytes
from knowledge_os.adapters.ingestion.strategies import get_chunk_strategy
from knowledge_os.adapters.messaging.event_bus import build_platform_event
from knowledge_os.domain.enums import EventTopic, GraphEdgeType, IngestionEventType
from knowledge_os.domain.utils import new_trace_id
from knowledge_os.ports.knowledge import (
    DerivedArtifactRepository,
    IngestionRunRepository,
    KnowledgeGraphRepository,
    KnowledgeRepository,
    VectorStore,
)
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.ports.repositories import EventBus
from knowledge_os.schemas.llm_policy import parse_llm_policy

logger = structlog.get_logger()


class IngestionService:
    """
    Phase 2 ingestion: idempotent, immutable assets, graph edges, event chain.
    Upload → extract → chunk → embed → graph index → derived artifacts → ready
    """

    def __init__(
        self,
        knowledge_repo: KnowledgeRepository,
        vector_store: VectorStore,
        graph_repo: KnowledgeGraphRepository,
        run_repo: IngestionRunRepository,
        artifact_repo: DerivedArtifactRepository,
        llm_gateway: LLMGateway | None,
        event_bus: EventBus,
        storage_root: Path,
        pipeline_version: str,
        use_dev_embeddings: bool = False,
        chunk_strategy: str = "structure_aware",
    ):
        self._knowledge_repo = knowledge_repo
        self._vector_store = vector_store
        self._graph_repo = graph_repo
        self._run_repo = run_repo
        self._artifact_repo = artifact_repo
        self._llm_gateway = llm_gateway
        self._event_bus = event_bus
        self._storage_root = storage_root
        self._pipeline_version = pipeline_version
        self._use_dev_embeddings = use_dev_embeddings
        self._chunk_strategy = chunk_strategy
        self._storage_root.mkdir(parents=True, exist_ok=True)

    async def ingest_upload(
        self,
        workspace_id: UUID,
        filename: str,
        content: bytes,
        mime_type: str,
        agent_config: dict | None = None,
        layer: str = "tenant",
        *,
        trace_id: str | None = None,
        actor_id: UUID | None = None,
        chunk_strategy: str | None = None,
    ):
        trace_id = trace_id or new_trace_id()
        content_hash = hashlib.sha256(content).hexdigest()

        existing = await self._knowledge_repo.find_asset_by_hash(
            workspace_id, content_hash, self._pipeline_version
        )
        if existing:
            logger.info("ingestion_idempotent_hit", asset_id=str(existing.id))
            return existing

        run = await self._run_repo.get_or_create(
            workspace_id, content_hash, self._pipeline_version
        )
        if run.asset_id and run.status == "completed":
            asset = await self._knowledge_repo.get_asset(run.asset_id)
            if asset:
                return asset

        asset = await self._knowledge_repo.create_asset(
            workspace_id=workspace_id,
            filename=filename,
            content_hash=content_hash,
            storage_path="",
            mime_type=mime_type,
            page_count=None,
            status="processing",
            layer=layer,
            ingest_run_id=run.id,
            pipeline_version=self._pipeline_version,
        )

        storage_dir = self._storage_root / str(workspace_id)
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_path = storage_dir / f"{asset.id}_{filename}"
        storage_path.write_bytes(content)
        await self._knowledge_repo.update_asset_status(asset.id, "processing")

        await self._emit(
            trace_id, workspace_id, actor_id, IngestionEventType.ASSET_UPLOADED,
            {"asset_id": str(asset.id), "filename": filename, "content_hash": content_hash, "layer": layer},
        )

        previous = await self._knowledge_repo.find_latest_by_filename(workspace_id, filename)
        if previous and previous.id != asset.id and previous.content_hash != content_hash:
            await self._graph_repo.add_edge(
                workspace_id=workspace_id,
                source_id=asset.id,
                source_type="knowledge_asset",
                target_id=previous.id,
                target_type="knowledge_asset",
                edge_type=GraphEdgeType.SUPERSEDES.value,
                metadata={"reason": "content_changed"},
            )
            await self._knowledge_repo.mark_superseded(previous.id, asset.id)
            await self._emit(
                trace_id, workspace_id, actor_id, IngestionEventType.ASSET_SUPERSEDED,
                {"new_asset_id": str(asset.id), "old_asset_id": str(previous.id)},
            )

        try:
            text, page_count = extract_text_from_bytes(content, mime_type, filename)
            strategy = get_chunk_strategy(chunk_strategy or self._chunk_strategy)
            chunks = strategy(text)
            model_id = "dev-embed"

            if agent_config and agent_config.get("schema_version") == "2.1":
                policy = parse_llm_policy(agent_config)
                model_id = policy.embedding.model.model_id

            chunk_ids: list[str] = []
            for tc in chunks:
                chunk = await self._knowledge_repo.create_chunk(
                    asset_id=asset.id,
                    workspace_id=workspace_id,
                    chunk_index=tc.chunk_index,
                    text=tc.text,
                    page=tc.page,
                    section=tc.section,
                    token_count=tc.token_count,
                    layer=layer,
                )
                chunk_ids.append(str(chunk.id))

                await self._graph_repo.add_edge(
                    workspace_id=workspace_id,
                    source_id=chunk.id,
                    source_type="knowledge_chunk",
                    target_id=asset.id,
                    target_type="knowledge_asset",
                    edge_type=GraphEdgeType.CITES.value,
                )

                embedding = await self._embed_text(tc.text, workspace_id, agent_config)
                await self._vector_store.upsert(
                    chunk_id=chunk.id,
                    workspace_id=workspace_id,
                    embedding=embedding,
                    model_id=model_id,
                    layer=layer,
                )

            await self._emit(
                trace_id, workspace_id, actor_id, IngestionEventType.CHUNK_CREATED,
                {"asset_id": str(asset.id), "chunk_count": len(chunks), "chunk_ids": chunk_ids[:10]},
            )
            await self._emit(
                trace_id, workspace_id, actor_id, IngestionEventType.EMBEDDING_COMPLETED,
                {"asset_id": str(asset.id), "model_id": model_id, "chunk_count": len(chunks)},
            )
            await self._emit(
                trace_id, workspace_id, actor_id, IngestionEventType.GRAPH_INDEXED,
                {"asset_id": str(asset.id), "edge_count": len(chunks)},
            )

            summary = await self._generate_summary(text, filename)
            artifact = await self._artifact_repo.create(
                workspace_id=workspace_id,
                source_asset_id=asset.id,
                artifact_type="summary",
                content={"text": summary, "filename": filename},
                layer=layer,
            )
            await self._graph_repo.add_edge(
                workspace_id=workspace_id,
                source_id=artifact.id,
                source_type="derived_artifact",
                target_id=asset.id,
                target_type="knowledge_asset",
                edge_type=GraphEdgeType.DERIVED_FROM.value,
            )
            await self._emit(
                trace_id, workspace_id, actor_id, IngestionEventType.DERIVED_READY,
                {"artifact_id": str(artifact.id), "artifact_type": "summary", "asset_id": str(asset.id)},
            )

            asset = await self._knowledge_repo.update_asset_status(asset.id, "ready")
            await self._run_repo.complete(run.id, asset.id)
            await self._emit(
                trace_id, workspace_id, actor_id, IngestionEventType.ASSET_READY,
                {
                    "asset_id": str(asset.id),
                    "chunk_count": len(chunks),
                    "page_count": page_count,
                    "version": {
                        "asset_id": str(asset.id),
                        "content_hash": content_hash,
                        "ingest_run_id": str(run.id),
                    },
                },
            )
            return asset

        except Exception as exc:
            logger.error("ingestion_failed", asset_id=str(asset.id), error=str(exc))
            await self._knowledge_repo.update_asset_status(asset.id, "failed")
            await self._run_repo.fail(run.id)
            raise

    async def ingest_platform_public(
        self,
        platform_workspace_id: UUID,
        filename: str,
        content: bytes,
        mime_type: str,
        agent_config: dict | None = None,
        *,
        trace_id: str | None = None,
    ):
        return await self.ingest_upload(
            workspace_id=platform_workspace_id,
            filename=filename,
            content=content,
            mime_type=mime_type,
            agent_config=agent_config,
            layer="platform_public",
            trace_id=trace_id,
        )

    async def _generate_summary(self, text: str, filename: str) -> str:
        words = text.split()
        preview = " ".join(words[:300])
        return f"Summary of {filename}: {preview}{'...' if len(words) > 300 else ''}"

    async def _embed_text(
        self, text: str, workspace_id: UUID, agent_config: dict | None
    ) -> list[float]:
        if self._use_dev_embeddings or self._llm_gateway is None:
            return dev_embed(text)

        if agent_config and agent_config.get("schema_version") == "2.1":
            from knowledge_os.domain.llm import EmbeddingRequest

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

    async def list_assets(self, workspace_id: UUID, layer: str | None = None):
        return await self._knowledge_repo.list_assets(workspace_id, layer=layer)

    async def get_asset_graph(self, asset_id: UUID):
        return await self._graph_repo.list_edges_for_asset(asset_id)

    async def get_derived_artifacts(self, asset_id: UUID):
        return await self._artifact_repo.list_for_asset(asset_id)
