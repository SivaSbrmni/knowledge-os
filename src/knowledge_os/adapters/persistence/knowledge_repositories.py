from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_os.adapters.persistence.models import (
    ChunkEmbeddingModel,
    KnowledgeAssetModel,
    KnowledgeChunkModel,
)
from knowledge_os.domain.knowledge import ChunkEmbedding, KnowledgeAsset, KnowledgeChunk
from knowledge_os.ports.knowledge import KnowledgeRepository, VectorStore


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
    ) -> KnowledgeAsset:
        model = KnowledgeAssetModel(
            workspace_id=workspace_id,
            filename=filename,
            content_hash=content_hash,
            storage_path=storage_path,
            mime_type=mime_type,
            page_count=page_count,
            status=status,
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

    async def get_asset(self, asset_id: UUID) -> KnowledgeAsset | None:
        model = await self._session.get(KnowledgeAssetModel, asset_id)
        return _to_asset(model) if model else None

    async def list_assets(self, workspace_id: UUID) -> list[KnowledgeAsset]:
        stmt = (
            select(KnowledgeAssetModel)
            .where(KnowledgeAssetModel.workspace_id == workspace_id)
            .order_by(KnowledgeAssetModel.created_at.desc())
        )
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
    ) -> KnowledgeChunk:
        model = KnowledgeChunkModel(
            asset_id=asset_id,
            workspace_id=workspace_id,
            chunk_index=chunk_index,
            text=text,
            page=page,
            section=section,
            token_count=token_count,
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
    ) -> ChunkEmbedding:
        stmt = select(ChunkEmbeddingModel).where(ChunkEmbeddingModel.chunk_id == chunk_id)
        existing = await self._session.scalar(stmt)
        if existing:
            existing.embedding = embedding
            existing.model_id = model_id
            existing.dimensions = len(embedding)
            await self._session.flush()
            return ChunkEmbedding(
                chunk_id=chunk_id,
                workspace_id=workspace_id,
                model_id=model_id,
                dimensions=len(embedding),
            )

        model = ChunkEmbeddingModel(
            chunk_id=chunk_id,
            workspace_id=workspace_id,
            model_id=model_id,
            dimensions=len(embedding),
            embedding=embedding,
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
    ) -> list[tuple[UUID, float]]:
        stmt = select(ChunkEmbeddingModel).where(
            ChunkEmbeddingModel.workspace_id == workspace_id
        )
        results = await self._session.scalars(stmt)
        scored: list[tuple[UUID, float]] = []
        for row in results:
            sim = _cosine_similarity(query_embedding, row.embedding)
            scored.append((row.chunk_id, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
