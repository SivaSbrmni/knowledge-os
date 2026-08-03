"""Tenant-scoped knowledge provider — retrieves from workspace vector index."""

from datetime import UTC, datetime
from uuid import UUID

from knowledge_os.domain.enums import KnowledgeLayer
from knowledge_os.domain.knowledge import EvidencePacket
from knowledge_os.ports.knowledge import KnowledgeProvider, KnowledgeRepository, VectorStore


class TenantKnowledgeProvider(KnowledgeProvider):
    def __init__(
        self,
        knowledge_repo: KnowledgeRepository,
        vector_store: VectorStore,
        embed_fn,
    ):
        self._knowledge_repo = knowledge_repo
        self._vector_store = vector_store
        self._embed_fn = embed_fn

    @property
    def provider_id(self) -> str:
        return "tenant_knowledge"

    async def can_answer(self, question: str, workspace_id: UUID) -> float:
        assets = await self._knowledge_repo.list_assets(workspace_id)
        ready = [a for a in assets if a.status == "ready"]
        if not ready:
            return 0.0
        return 0.9

    async def retrieve_evidence(
        self,
        question: str,
        workspace_id: UUID,
        top_k: int = 5,
    ) -> list[EvidencePacket]:
        query_vec = await self._embed_fn(question)
        hits = await self._vector_store.search(workspace_id, query_vec, top_k=top_k)
        packets: list[EvidencePacket] = []
        now = datetime.now(UTC).isoformat()

        for chunk_id, score in hits:
            chunk = await self._knowledge_repo.get_chunk(chunk_id)
            if chunk is None:
                continue
            asset = await self._knowledge_repo.get_asset(chunk.asset_id)
            if asset is None:
                continue

            packets.append(
                EvidencePacket(
                    claim="",
                    chunk_id=chunk.id,
                    document_id=asset.id,
                    source_id=asset.id,
                    layer=KnowledgeLayer.TENANT.value,
                    tenant_scope=workspace_id,
                    text=chunk.text,
                    page=chunk.page,
                    section=chunk.section,
                    version={
                        "asset_id": str(asset.id),
                        "content_hash": asset.content_hash,
                    },
                    timestamp=now,
                    confidence=float(score),
                    freshness=1.0,
                    trust_level="tenant",
                    authority_flag=False,
                    reasoning_path=["tenant_knowledge_provider"],
                )
            )
        return packets
