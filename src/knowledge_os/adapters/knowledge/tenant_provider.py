"""Tenant + platform public knowledge retrieval."""

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
        platform_workspace_id: UUID | None = None,
    ):
        self._knowledge_repo = knowledge_repo
        self._vector_store = vector_store
        self._embed_fn = embed_fn
        self._platform_workspace_id = platform_workspace_id

    @property
    def provider_id(self) -> str:
        return "tenant_knowledge"

    async def can_answer(self, question: str, workspace_id: UUID) -> float:
        assets = await self._knowledge_repo.list_assets(workspace_id)
        ready = [a for a in assets if a.status == "ready" and not a.superseded_by]
        if self._platform_workspace_id:
            platform_assets = await self._knowledge_repo.list_assets(
                self._platform_workspace_id, layer=KnowledgeLayer.PLATFORM_PUBLIC.value
            )
            ready.extend([a for a in platform_assets if a.status == "ready"])
        if not ready:
            return 0.0
        return 0.9

    async def retrieve_evidence(
        self,
        question: str,
        workspace_id: UUID,
        top_k: int = 5,
        allowed_layers: list[str] | None = None,
        platform_workspace_id: UUID | None = None,
    ) -> list[EvidencePacket]:
        query_vec = await self._embed_fn(question)
        layers = allowed_layers or [KnowledgeLayer.TENANT.value]
        extra_ws = []
        platform_id = platform_workspace_id or self._platform_workspace_id
        if platform_id and KnowledgeLayer.PLATFORM_PUBLIC.value in layers:
            extra_ws.append(platform_id)

        hits = await self._vector_store.search(
            workspace_id,
            query_vec,
            top_k=top_k,
            layers=layers,
            extra_workspace_ids=extra_ws or None,
        )
        packets: list[EvidencePacket] = []
        now = datetime.now(UTC).isoformat()

        for chunk_id, score in hits:
            chunk = await self._knowledge_repo.get_chunk(chunk_id)
            if chunk is None:
                continue
            asset = await self._knowledge_repo.get_asset(chunk.asset_id)
            if asset is None or asset.superseded_by:
                continue

            packets.append(
                EvidencePacket(
                    claim="",
                    chunk_id=chunk.id,
                    document_id=asset.id,
                    source_id=asset.id,
                    layer=chunk.layer,
                    tenant_scope=workspace_id,
                    text=chunk.text,
                    page=chunk.page,
                    section=chunk.section,
                    version={
                        "asset_id": str(asset.id),
                        "content_hash": asset.content_hash,
                        "pipeline_version": asset.pipeline_version,
                    },
                    timestamp=now,
                    confidence=float(score),
                    freshness=1.0,
                    trust_level=chunk.layer,
                    authority_flag=chunk.layer == KnowledgeLayer.PLATFORM_PUBLIC.value,
                    reasoning_path=["tenant_knowledge_provider"],
                )
            )
        return packets
