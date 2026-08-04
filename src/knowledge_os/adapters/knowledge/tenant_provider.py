"""Tenant + platform public knowledge retrieval."""

from datetime import UTC, datetime
from uuid import UUID

from knowledge_os.domain.enums import KnowledgeLayer
from knowledge_os.domain.knowledge import EvidencePacket
from knowledge_os.domain.llm import EmbeddingRequest
from knowledge_os.ports.knowledge import KnowledgeProvider, KnowledgeRepository, VectorStore
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.schemas.llm_policy import parse_llm_policy
from knowledge_os.services.trust_evaluator import compute_freshness


class TenantKnowledgeProvider(KnowledgeProvider):
    def __init__(
        self,
        knowledge_repo: KnowledgeRepository,
        vector_store: VectorStore,
        embed_fn,
        platform_workspace_id: UUID | None = None,
        use_dev_embeddings: bool = False,
        llm_gateway: LLMGateway | None = None,
    ):
        self._knowledge_repo = knowledge_repo
        self._vector_store = vector_store
        self._embed_fn = embed_fn
        self._platform_workspace_id = platform_workspace_id
        self._use_dev_embeddings = use_dev_embeddings
        self._llm_gateway = llm_gateway

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
        knowledge_policy: dict | None = None,
        agent_config: dict | None = None,
    ) -> list[EvidencePacket]:
        policy = knowledge_policy or {}
        max_age_days = policy.get("max_evidence_age_days")
        freshness_requirement = policy.get("freshness_requirement", "relaxed")
        authority_preference = policy.get("authority_preference", "balanced")

        query_vec = await self._embed_query(question, workspace_id, agent_config)
        layers = allowed_layers or [KnowledgeLayer.TENANT.value]
        extra_ws = []
        platform_id = platform_workspace_id or self._platform_workspace_id
        if platform_id and KnowledgeLayer.PLATFORM_PUBLIC.value in layers:
            extra_ws.append(platform_id)

        hits = await self._vector_store.search(
            workspace_id,
            query_vec,
            top_k=top_k * 2,
            layers=layers,
            extra_workspace_ids=extra_ws or None,
        )
        if self._use_dev_embeddings and hits:
            hits = [
                (chunk_id, max(0.75, 0.95 - index * 0.08))
                for index, (chunk_id, _) in enumerate(hits)
            ]

        packets: list[EvidencePacket] = []
        now = datetime.now(UTC)

        for chunk_id, score in hits:
            chunk = await self._knowledge_repo.get_chunk(chunk_id)
            if chunk is None:
                continue
            asset = await self._knowledge_repo.get_asset(chunk.asset_id)
            if asset is None or asset.superseded_by:
                continue

            age_days = (now - asset.created_at).total_seconds() / 86400
            freshness = compute_freshness(age_days, max_age_days)
            if freshness_requirement == "strict" and freshness == 0.0:
                continue

            claim_text = chunk.text.split(".")[0].strip()[:200]
            packets.append(
                EvidencePacket(
                    claim=claim_text,
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
                    timestamp=now.isoformat(),
                    confidence=float(score),
                    freshness=freshness,
                    trust_level=chunk.layer,
                    authority_flag=chunk.layer == KnowledgeLayer.PLATFORM_PUBLIC.value,
                    reasoning_path=["tenant_knowledge_provider"],
                )
            )

        if authority_preference == "government_sources_first":
            packets.sort(key=lambda p: (not p.authority_flag, -p.confidence))

        return packets[:top_k]

    async def _embed_query(
        self, question: str, workspace_id: UUID, agent_config: dict | None
    ) -> list[float]:
        if (
            self._llm_gateway
            and agent_config
            and agent_config.get("schema_version") == "2.1"
        ):
            try:
                llm_policy = parse_llm_policy(agent_config)
                response = await self._llm_gateway.embed(
                    llm_policy,
                    workspace_id,
                    EmbeddingRequest(
                        texts=[question],
                        model_id=llm_policy.embedding.model.model_id,
                    ),
                )
                return response.embeddings[0]
            except Exception:
                pass
        return await self._embed_fn(question)
