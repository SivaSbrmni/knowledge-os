"""Mesh execution context passed between agentic nodes."""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from knowledge_os.domain.knowledge import EvidencePacket, ReasonedClaim, TrustVector


@dataclass
class MeshContext:
    """Mutable state bag flowing through the mesh DAG."""

    question: str
    workspace_id: UUID
    agent_config: dict[str, Any]
    session_messages: list[dict[str, Any]] = field(default_factory=list)
    trace_id: str = ""

    intent: str = "question"
    can_answer_score: float = 0.0
    packets: list[EvidencePacket] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    claims: list[ReasonedClaim] = field(default_factory=list)
    answer: str = ""
    llm_used: bool = False
    citations: list[dict[str, Any]] = field(default_factory=list)
    trust: TrustVector | None = None

    withheld: bool = False
    withhold_message: str = ""
    show_trust_vector: bool = True

    node_trace: list[str] = field(default_factory=list)
    stop: bool = False

    @property
    def reasoning_policy(self) -> dict[str, Any]:
        return self.agent_config.get("reasoning_policy", {})

    @property
    def trust_policy(self) -> dict[str, Any]:
        return self.agent_config.get("trust_policy", {})

    @property
    def knowledge_policy(self) -> dict[str, Any]:
        return self.agent_config.get("knowledge_policy", {})

    def halt(self, message: str) -> None:
        self.withheld = True
        self.withhold_message = message
        self.stop = True
