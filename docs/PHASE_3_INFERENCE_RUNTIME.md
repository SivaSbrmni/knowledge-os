# Phase 3 — Inference Runtime

Phase 3 upgrades the query path from a heuristic skeleton to a **policy-driven inference runtime**.

## Components

| Component | Path | Role |
|-----------|------|------|
| **Reasoning Agent** | `services/reasoning_agent.py` | LLM-grounded answers, intent modes, session memory |
| **Trust Evaluator** | `services/trust_evaluator.py` | Conflicts, freshness-weighted trust, thresholds |
| **Query Pipeline** | `services/query_pipeline.py` | Orchestrates intent → retrieve → reason → cite → trust |

## Policy enforcement

### `reasoning_policy`
- `min_evidence_packets` — withhold when insufficient evidence
- `grounding_required` — withhold when claims lack chunk references
- `allow_foundation_model_recall` — controls outside-knowledge instructions
- `conflict_behavior` — `surface_and_explain` | `prefer_authority` | `withhold`

### `trust_policy`
- `min_source_trust`, `min_groundedness`, `withhold_below_threshold`
- `show_trust_vector` — hides trust payload in API when `false`

### `knowledge_policy`
- `allowed_layers` — namespace filtering (tenant + platform public)
- `max_evidence_age_days` + `freshness_requirement` — stale asset filtering
- `authority_preference` — rank platform-public evidence first

### `memory_policy`
- `session_memory` — prior turns included in reasoning prompt

## LLM integration

When `USE_DEV_EMBEDDINGS=false` and workspace credentials are configured:
- Query embeddings use `llm_policy.embedding` via `LLMGateway`
- Reasoning uses `llm_policy.inference` with fallback chain

With `USE_DEV_EMBEDDINGS=true` (default for local dev):
- Hash-based dev embeddings and excerpt fallback reasoning

## Verification

```bash
alembic upgrade head
python scripts/ensure_platform_workspace.py
python scripts/verify_e2e.py
pytest tests/ -v
```
