# Phase 4 — Agentic Mesh

Phase 4 replaces the monolithic query pipeline with a **configurable DAG of independently deployable mesh nodes**.

## Architecture

```
Intent Analyzer → Knowledge Router → Conflict Detector → Reasoning Agent
    → Citation Builder → Trust Evaluator → Response Assembler
```

Each node:
- Receives and returns a `MeshContext`
- Can short-circuit the DAG via `ctx.halt(message)`
- Emits `mesh.node.completed` events on the platform event bus

## Configuration

Optional `mesh_policy` in agent config:

```json
{
  "mesh_policy": {
    "enabled": true,
    "dag": [
      "intent_analyzer",
      "knowledge_router",
      "conflict_detector",
      "reasoning_agent",
      "citation_builder",
      "trust_evaluator",
      "response_assembler"
    ]
  }
}
```

When omitted, the default DAG above is used. Set `"enabled": false` to keep default DAG (same behavior).

## Files

| Path | Role |
|------|------|
| `domain/mesh.py` | `MeshContext` state bag |
| `ports/mesh.py` | `MeshNode` protocol |
| `services/mesh/nodes.py` | Seven default nodes |
| `services/mesh/orchestrator.py` | DAG runner + event emission |
| `services/query_pipeline.py` | Backward-compatible facade |

## Verification

```bash
pytest tests/test_mesh_orchestrator.py tests/test_query_pipeline.py -v
python scripts/verify_e2e.py
```
