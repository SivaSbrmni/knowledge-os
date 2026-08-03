from abc import ABC, abstractmethod
from uuid import UUID

from knowledge_os.domain.knowledge import (
    ChunkEmbedding,
    EvidencePacket,
    KnowledgeAsset,
    KnowledgeChunk,
)


class KnowledgeRepository(ABC):
    @abstractmethod
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
        pass

    @abstractmethod
    async def update_asset_status(self, asset_id: UUID, status: str) -> KnowledgeAsset:
        pass

    @abstractmethod
    async def get_asset(self, asset_id: UUID) -> KnowledgeAsset | None:
        pass

    @abstractmethod
    async def list_assets(self, workspace_id: UUID) -> list[KnowledgeAsset]:
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def get_chunk(self, chunk_id: UUID) -> KnowledgeChunk | None:
        pass

    @abstractmethod
    async def list_chunks_for_asset(self, asset_id: UUID) -> list[KnowledgeChunk]:
        pass


class VectorStore(ABC):
    @abstractmethod
    async def upsert(
        self,
        chunk_id: UUID,
        workspace_id: UUID,
        embedding: list[float],
        model_id: str,
    ) -> ChunkEmbedding:
        pass

    @abstractmethod
    async def search(
        self,
        workspace_id: UUID,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[tuple[UUID, float]]:
        """Return (chunk_id, similarity_score) pairs."""
        pass


class KnowledgeProvider(ABC):
    """Port for knowledge retrieval — TenantFileProvider in Phase 1."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        pass

    @abstractmethod
    async def can_answer(self, question: str, workspace_id: UUID) -> float:
        pass

    @abstractmethod
    async def retrieve_evidence(
        self,
        question: str,
        workspace_id: UUID,
        top_k: int = 5,
    ) -> list[EvidencePacket]:
        pass
