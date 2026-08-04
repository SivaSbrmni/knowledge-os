"""Trust evaluation — conflicts, freshness-weighted source trust, policy thresholds."""

import re

from knowledge_os.domain.knowledge import EvidencePacket, ReasonedClaim, TrustVector

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "of", "in", "to", "and", "or", "for",
    "on", "at", "by", "with", "as", "it", "this", "that", "from", "be", "has", "have",
})
_NEGATION_MARKERS = (" not ", " never ", " incorrect", " false", " unlike ", " cannot ", " no longer ")


def compute_freshness(age_days: float, max_age_days: int | None) -> float:
    if max_age_days is None or max_age_days <= 0:
        return 1.0
    if age_days > max_age_days:
        return 0.0
    return max(0.0, 1.0 - (age_days / max_age_days))


def detect_conflicts(packets: list[EvidencePacket]) -> list[str]:
    """Heuristic conflict detection across evidence packets."""
    conflicts: list[str] = []
    for i, left in enumerate(packets):
        for right in packets[i + 1 :]:
            if left.document_id == right.document_id:
                continue
            left_words = {w for w in re.findall(r"[a-z]{4,}", left.text.lower())} - _STOPWORDS
            right_words = {w for w in re.findall(r"[a-z]{4,}", right.text.lower())} - _STOPWORDS
            overlap = left_words & right_words
            if len(overlap) < 2:
                continue
            left_neg = any(marker in f" {left.text.lower()} " for marker in _NEGATION_MARKERS)
            right_neg = any(marker in f" {right.text.lower()} " for marker in _NEGATION_MARKERS)
            if left_neg != right_neg:
                conflicts.append(
                    f"Contradicting evidence between documents "
                    f"{left.document_id} and {right.document_id} "
                    f"(shared terms: {', '.join(sorted(overlap)[:3])})"
                )
    return conflicts


def evaluate_trust(
    packets: list[EvidencePacket],
    claims: list[ReasonedClaim],
    trust_policy: dict,
    *,
    conflicts: list[str] | None = None,
    llm_used: bool = False,
    grounding_required: bool = True,
    conflicts_block_threshold: bool = True,
) -> TrustVector:
    min_source = trust_policy.get("min_source_trust", 0.7)
    min_grounded = trust_policy.get("min_groundedness", 0.8)
    conflict_list = conflicts or []

    if packets:
        weighted = [p.confidence * p.freshness for p in packets]
        source_trust = sum(weighted) / len(weighted)
    else:
        source_trust = 0.0

    retrieval_trust = min(1.0, len(packets) / 3.0)

    grounded = sum(1 for claim in claims if claim.evidence_packet_ids)
    groundedness = grounded / len(claims) if claims else 0.0

    base_reasoning = 0.9 if llm_used else 0.65
    grounding_bonus = 0.1 if groundedness >= min_grounded else 0.0
    conflict_penalty = min(0.3, 0.1 * len(conflict_list))
    reasoning_trust = max(0.0, min(1.0, base_reasoning + grounding_bonus - conflict_penalty))

    overall = (source_trust + retrieval_trust + reasoning_trust + groundedness) / 4.0
    threshold_met = (
        source_trust >= min_source
        and groundedness >= min_grounded
        and len(packets) > 0
        and (not grounding_required or grounded == len(claims) or not claims)
        and (not conflict_list or not conflicts_block_threshold)
    )

    explanation_parts = [
        f"Grounded {grounded}/{len(claims)} claims from {len(packets)} evidence packets."
    ]
    if llm_used:
        explanation_parts.append("Reasoned via LLM gateway.")
    else:
        explanation_parts.append("Reasoned via evidence excerpt fallback.")
    if conflict_list:
        explanation_parts.append(f"{len(conflict_list)} conflict(s) detected.")

    return TrustVector(
        source_trust=round(source_trust, 3),
        retrieval_trust=round(retrieval_trust, 3),
        reasoning_trust=round(reasoning_trust, 3),
        groundedness=round(groundedness, 3),
        overall=round(overall, 3),
        threshold_met=threshold_met,
        explanation=" ".join(explanation_parts),
        conflicts=conflict_list,
    )
