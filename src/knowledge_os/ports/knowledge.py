from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from knowledge_os.domain.knowledge import (
    ChunkEmbedding,
    DerivedArtifact,
    EvidencePacket,
    IngestionRun,
    KnowledgeAsset,
    KnowledgeChunk,
    KnowledgeEdge,
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
        layer: str = "tenant",
        ingest_run_id: UUID | None = None,
        pipeline_version: str = "1.0",
    ) -> KnowledgeAsset:
        pass

    @abstractmethod
    async def update_asset_status(self, asset_id: UUID, status: str) -> KnowledgeAsset:
        pass

    @abstractmethod
    async def mark_superseded(self, old_asset_id: UUID, new_asset_id: UUID) -> KnowledgeAsset:
        pass

    @abstractmethod
    async def get_asset(self, asset_id: UUID) -> KnowledgeAsset | None:
        pass

    @abstractmethod
    async def find_asset_by_hash(
        self, workspace_id: UUID, content_hash: str, pipeline_version: str
    ) -> KnowledgeAsset | None:
        pass

    @abstractmethod
    async def find_latest_by_filename(self, workspace_id: UUID, filename: str) -> KnowledgeAsset | None:
        pass

    @abstractmethod
    async def list_assets(self, workspace_id: UUID, layer: str | None = None) -> list[KnowledgeAsset]:
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
        layer: str = "tenant",
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
        layer: str = "tenant",
    ) -> ChunkEmbedding:
        pass

    @abstractmethod
    async def search(
        self,
        workspace_id: UUID,
        query_embedding: list[float],
        top_k: int = 5,
        layers: list[str] | None = None,
        extra_workspace_ids: list[UUID] | None = None,
    ) -> list[tuple[UUID, float]]:
        pass


class KnowledgeGraphRepository(ABC):
    @abstractmethod
    async def add_edge(
        self,
        workspace_id: UUID,
        source_id: UUID,
        source_type: str,
        target_id: UUID,
        target_type: str,
        edge_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeEdge:
        pass

    @abstractmethod
    async def list_edges_for_source(
        self, source_id: UUID, edge_type: str | None = None
    ) -> list[KnowledgeEdge]:
        pass

    @abstractmethod
    async def list_edges_for_asset(self, asset_id: UUID) -> list[KnowledgeEdge]:
        pass


class IngestionRunRepository(ABC):
    @abstractmethod
    async def get_or_create(
        self, workspace_id: UUID, content_hash: str, pipeline_version: str
    ) -> IngestionRun:
        pass

    @abstractmethod
    async def complete(self, run_id: UUID, asset_id: UUID) -> IngestionRun:
        pass

    @abstractmethod
    async def fail(self, run_id: UUID) -> IngestionRun:
        pass


class DerivedArtifactRepository(ABC):
    @abstractmethod
    async def create(
        self,
        workspace_id: UUID,
        source_asset_id: UUID,
        artifact_type: str,
        content: dict[str, Any],
        layer: str = "tenant",
    ) -> DerivedArtifact:
        pass

    @abstractmethod
    async def list_for_asset(self, source_asset_id: UUID) -> list[DerivedArtifact]:
        pass


class KnowledgeProvider(ABC):
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
        allowed_layers: list[str] | None = None,
        platform_workspace_id: UUID | None = None,
    ) -> list[EvidencePacket]:
        pass
