from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_os.adapters.persistence.models import (
    ChunkEmbeddingModel,
    DerivedArtifactModel,
    IngestionRunModel,
    KnowledgeAssetModel,
    KnowledgeChunkModel,
    KnowledgeGraphEdgeModel,
)
from knowledge_os.domain.knowledge import (
    ChunkEmbedding,
    DerivedArtifact,
    IngestionRun,
    KnowledgeAsset,
    KnowledgeChunk,
    KnowledgeEdge,
)
from knowledge_os.ports.knowledge import (
    DerivedArtifactRepository,
    IngestionRunRepository,
    KnowledgeGraphRepository,
    KnowledgeRepository,
    VectorStore,
)


def _to_asset(m: KnowledgeAssetModel) -> KnowledgeAsset:
    return KnowledgeAsset(
        id=m.id,
        workspace_id=m.workspace_id,
        filename=m.filename,
        content_hash=m.content_hash,
        storage_path=m.storage_path,
        mime_type=m.mime_type,
        page_count=m.page_count,
        status=m.status,
        layer=m.layer,
        ingest_run_id=m.ingest_run_id,
        pipeline_version=m.pipeline_version,
        superseded_by=m.superseded_by,
        created_at=m.created_at,
    )


def _to_chunk(m: KnowledgeChunkModel) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=m.id,
        asset_id=m.asset_id,
        workspace_id=m.workspace_id,
        chunk_index=m.chunk_index,
        text=m.text,
        page=m.page,
        section=m.section,
        token_count=m.token_count,
        layer=m.layer,
        created_at=m.created_at,
    )


def _to_edge(m: KnowledgeGraphEdgeModel) -> KnowledgeEdge:
    return KnowledgeEdge(
        id=m.id,
        workspace_id=m.workspace_id,
        source_id=m.source_id,
        source_type=m.source_type,
        target_id=m.target_id,
        target_type=m.target_type,
        edge_type=m.edge_type,
        metadata=m.edge_metadata,
        created_at=m.created_at,
    )


def _to_artifact(m: DerivedArtifactModel) -> DerivedArtifact:
    return DerivedArtifact(
        id=m.id,
        workspace_id=m.workspace_id,
        source_asset_id=m.source_asset_id,
        artifact_type=m.artifact_type,
        content=m.content,
        status=m.status,
        layer=m.layer,
        created_at=m.created_at,
    )


def _to_run(m: IngestionRunModel) -> IngestionRun:
    return IngestionRun(
        id=m.id,
        workspace_id=m.workspace_id,
        content_hash=m.content_hash,
        pipeline_version=m.pipeline_version,
        asset_id=m.asset_id,
        status=m.status,
        created_at=m.created_at,
    )


class PostgresKnowledgeRepository(KnowledgeRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_asset(
        self,
        workspace_id: UUID,
        filename: str,
        content_hash: str,
        storage_path: str,
        mime_type: str,
        page_count: int | None,
        status: str = "processing",
        layer: str = "tenant",
        ingest_run_id: UUID | None = None,
        pipeline_version: str = "1.0",
    ) -> KnowledgeAsset:
        model = KnowledgeAssetModel(
            workspace_id=workspace_id,
            filename=filename,
            content_hash=content_hash,
            storage_path=storage_path,
            mime_type=mime_type,
            page_count=page_count,
            status=status,
            layer=layer,
            ingest_run_id=ingest_run_id,
            pipeline_version=pipeline_version,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_asset(model)

    async def update_asset_status(self, asset_id: UUID, status: str) -> KnowledgeAsset:
        model = await self._session.get(KnowledgeAssetModel, asset_id)
        if model is None:
            raise ValueError("Asset not found")
        model.status = status
        await self._session.flush()
        return _to_asset(model)

    async def mark_superseded(self, old_asset_id: UUID, new_asset_id: UUID) -> KnowledgeAsset:
        await self._session.execute(
            update(KnowledgeAssetModel)
            .where(KnowledgeAssetModel.id == old_asset_id)
            .values(superseded_by=new_asset_id, status="superseded")
        )
        await self._session.flush()
        model = await self._session.get(KnowledgeAssetModel, old_asset_id)
        assert model is not None
        return _to_asset(model)

    async def get_asset(self, asset_id: UUID) -> KnowledgeAsset | None:
        model = await self._session.get(KnowledgeAssetModel, asset_id)
        return _to_asset(model) if model else None

    async def find_asset_by_hash(
        self, workspace_id: UUID, content_hash: str, pipeline_version: str
    ) -> KnowledgeAsset | None:
        stmt = select(KnowledgeAssetModel).where(
            KnowledgeAssetModel.workspace_id == workspace_id,
            KnowledgeAssetModel.content_hash == content_hash,
            KnowledgeAssetModel.pipeline_version == pipeline_version,
            KnowledgeAssetModel.status == "ready",
            KnowledgeAssetModel.superseded_by.is_(None),
        )
        model = await self._session.scalar(stmt)
        return _to_asset(model) if model else None

    async def find_latest_by_filename(self, workspace_id: UUID, filename: str) -> KnowledgeAsset | None:
        stmt = (
            select(KnowledgeAssetModel)
            .where(
                KnowledgeAssetModel.workspace_id == workspace_id,
                KnowledgeAssetModel.filename == filename,
                KnowledgeAssetModel.superseded_by.is_(None),
            )
            .order_by(KnowledgeAssetModel.created_at.desc())
        )
        model = await self._session.scalar(stmt)
        return _to_asset(model) if model else None

    async def list_assets(self, workspace_id: UUID, layer: str | None = None) -> list[KnowledgeAsset]:
        stmt = select(KnowledgeAssetModel).where(KnowledgeAssetModel.workspace_id == workspace_id)
        if layer:
            stmt = stmt.where(KnowledgeAssetModel.layer == layer)
        stmt = stmt.order_by(KnowledgeAssetModel.created_at.desc())
        results = await self._session.scalars(stmt)
        return [_to_asset(r) for r in results]

    async def create_chunk(
        self,
        asset_id: UUID,
        workspace_id: UUID,
        chunk_index: int,
        text: str,
        page: int | None,
        section: str | None,
        token_count: int,
        layer: str = "tenant",
    ) -> KnowledgeChunk:
        model = KnowledgeChunkModel(
            asset_id=asset_id,
            workspace_id=workspace_id,
            chunk_index=chunk_index,
            text=text,
            page=page,
            section=section,
            token_count=token_count,
            layer=layer,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_chunk(model)

    async def get_chunk(self, chunk_id: UUID) -> KnowledgeChunk | None:
        model = await self._session.get(KnowledgeChunkModel, chunk_id)
        return _to_chunk(model) if model else None

    async def list_chunks_for_asset(self, asset_id: UUID) -> list[KnowledgeChunk]:
        stmt = (
            select(KnowledgeChunkModel)
            .where(KnowledgeChunkModel.asset_id == asset_id)
            .order_by(KnowledgeChunkModel.chunk_index)
        )
        results = await self._session.scalars(stmt)
        return [_to_chunk(r) for r in results]


class PostgresVectorStore(VectorStore):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert(
        self,
        chunk_id: UUID,
        workspace_id: UUID,
        embedding: list[float],
        model_id: str,
        layer: str = "tenant",
    ) -> ChunkEmbedding:
        stmt = select(ChunkEmbeddingModel).where(ChunkEmbeddingModel.chunk_id == chunk_id)
        existing = await self._session.scalar(stmt)
        if existing:
            existing.embedding = embedding
            existing.model_id = model_id
            existing.dimensions = len(embedding)
            existing.layer = layer
            await self._session.flush()
        else:
            model = ChunkEmbeddingModel(
                chunk_id=chunk_id,
                workspace_id=workspace_id,
                model_id=model_id,
                dimensions=len(embedding),
                embedding=embedding,
                layer=layer,
            )
            self._session.add(model)
            await self._session.flush()
        return ChunkEmbedding(
            chunk_id=chunk_id,
            workspace_id=workspace_id,
            model_id=model_id,
            dimensions=len(embedding),
        )

    async def search(
        self,
        workspace_id: UUID,
        query_embedding: list[float],
        top_k: int = 5,
        layers: list[str] | None = None,
        extra_workspace_ids: list[UUID] | None = None,
    ) -> list[tuple[UUID, float]]:
        workspace_ids = [workspace_id]
        if extra_workspace_ids:
            workspace_ids.extend(extra_workspace_ids)

        stmt = select(ChunkEmbeddingModel).where(
            ChunkEmbeddingModel.workspace_id.in_(workspace_ids)
        )
        if layers:
            stmt = stmt.where(ChunkEmbeddingModel.layer.in_(layers))

        results = await self._session.scalars(stmt)
        scored: list[tuple[UUID, float]] = []
        for row in results:
            sim = _cosine_similarity(query_embedding, row.embedding)
            scored.append((row.chunk_id, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


class PostgresKnowledgeGraphRepository(KnowledgeGraphRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_edge(
        self,
        workspace_id: UUID,
        source_id: UUID,
        source_type: str,
        target_id: UUID,
        target_type: str,
        edge_type: str,
        metadata: dict | None = None,
    ) -> KnowledgeEdge:
        model = KnowledgeGraphEdgeModel(
            workspace_id=workspace_id,
            source_id=source_id,
            source_type=source_type,
            target_id=target_id,
            target_type=target_type,
            edge_type=edge_type,
            edge_metadata=metadata or {},
        )
        self._session.add(model)
        await self._session.flush()
        return _to_edge(model)

    async def list_edges_for_source(
        self, source_id: UUID, edge_type: str | None = None
    ) -> list[KnowledgeEdge]:
        stmt = select(KnowledgeGraphEdgeModel).where(KnowledgeGraphEdgeModel.source_id == source_id)
        if edge_type:
            stmt = stmt.where(KnowledgeGraphEdgeModel.edge_type == edge_type)
        results = await self._session.scalars(stmt)
        return [_to_edge(r) for r in results]

    async def list_edges_for_asset(self, asset_id: UUID) -> list[KnowledgeEdge]:
        stmt = select(KnowledgeGraphEdgeModel).where(
            (KnowledgeGraphEdgeModel.source_id == asset_id)
            | (KnowledgeGraphEdgeModel.target_id == asset_id)
        )
        results = await self._session.scalars(stmt)
        return [_to_edge(r) for r in results]


class PostgresIngestionRunRepository(IngestionRunRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_or_create(
        self, workspace_id: UUID, content_hash: str, pipeline_version: str
    ) -> IngestionRun:
        stmt = select(IngestionRunModel).where(
            IngestionRunModel.workspace_id == workspace_id,
            IngestionRunModel.content_hash == content_hash,
            IngestionRunModel.pipeline_version == pipeline_version,
        )
        existing = await self._session.scalar(stmt)
        if existing:
            return _to_run(existing)

        model = IngestionRunModel(
            id=uuid4(),
            workspace_id=workspace_id,
            content_hash=content_hash,
            pipeline_version=pipeline_version,
            status="processing",
        )
        self._session.add(model)
        await self._session.flush()
        return _to_run(model)

    async def complete(self, run_id: UUID, asset_id: UUID) -> IngestionRun:
        model = await self._session.get(IngestionRunModel, run_id)
        if model is None:
            raise ValueError("Ingestion run not found")
        model.status = "completed"
        model.asset_id = asset_id
        await self._session.flush()
        return _to_run(model)

    async def fail(self, run_id: UUID) -> IngestionRun:
        model = await self._session.get(IngestionRunModel, run_id)
        if model is None:
            raise ValueError("Ingestion run not found")
        model.status = "failed"
        await self._session.flush()
        return _to_run(model)


class PostgresDerivedArtifactRepository(DerivedArtifactRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        workspace_id: UUID,
        source_asset_id: UUID,
        artifact_type: str,
        content: dict,
        layer: str = "tenant",
    ) -> DerivedArtifact:
        model = DerivedArtifactModel(
            workspace_id=workspace_id,
            source_asset_id=source_asset_id,
            artifact_type=artifact_type,
            content=content,
            status="ready",
            layer=layer,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_artifact(model)

    async def list_for_asset(self, source_asset_id: UUID) -> list[DerivedArtifact]:
        stmt = select(DerivedArtifactModel).where(
            DerivedArtifactModel.source_asset_id == source_asset_id
        )
        results = await self._session.scalars(stmt)
        return [_to_artifact(r) for r in results]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
