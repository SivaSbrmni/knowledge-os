# Open-Source LLM Agent Design

This document defines how Knowledge OS agents are built around **open-source LLMs** (Llama, Mistral, Qwen, etc.) hosted via token-authenticated providers.

## Core Principle

> **Agents are configuration. LLMs are replaceable adapters. Tokens never live in agent YAML.**

The Reasoning Agent (Phase 3+) calls the **LLM Gateway**, which reads the agent's `llm_policy` and routes to the correct open-model provider using workspace-scoped credentials.

## Architecture

```
Agent Config (llm_policy)
        │
        ▼
  LLM Gateway ──► Credential Store (encrypted PAT/API keys)
        │
        ├──► Together  (Llama 3.3 70B)
        ├──► Groq      (Llama 3.3 70B fallback)
        ├──► Ollama    (local Llama, no token)
        └──► HuggingFace (BGE embeddings, PAT)
```

## Agent Schema v2.1 — `llm_policy`

Every new agent **must** use schema version `2.1` with an `llm_policy` block:

| Field | Purpose |
|-------|---------|
| `require_open_source` | Enforce `open_source: true` on all models |
| `inference.primary` | Main LLM endpoint (provider + model + credential_ref) |
| `inference.fallbacks` | Ordered fallback providers if primary fails |
| `embedding` | Open-source embedding model endpoint |

### Supported Providers

| Provider | Auth | Typical Use |
|----------|------|-------------|
| `together` | API key | Llama 3.3 70B hosted |
| `groq` | API key | Fast Llama inference |
| `ollama` | none | Local/open-weight models |
| `huggingface` | Personal Access Token | Embeddings + inference |
| `openrouter` | API key | Multi-model routing |
| `fireworks` | API key | Llama fine-tunes |
| `custom_openai_compatible` | API key | Self-hosted vLLM, TGI, etc. |

### Credential References

Tokens are stored via the Credential API — **never in agent config**:

```bash
POST /api/v1/workspaces/{id}/credentials
{
  "credential_ref": "together-prod",
  "provider": "together",
  "auth_type": "api_key",
  "secret": "your-together-api-key",
  "description": "Together.ai production key"
}
```

The agent references it:

```json
"credential_ref": "together-prod"
```

## Example: UPSC Mentor

See `examples/upsc-mentor-agent.json`:

- **Primary**: Llama 3.3 70B on Together
- **Fallback 1**: Llama 3.3 70B on Groq
- **Fallback 2**: Local Llama 3.3 via Ollama
- **Embeddings**: BGE-large on HuggingFace (PAT)

## Validation Flow

Before activating an agent:

1. JSON Schema validation (v2.1)
2. Open-source policy enforcement
3. Credential existence check (`validate-llm-policy` endpoint)

```bash
POST /api/v1/workspaces/{id}/agents/validate-llm-policy
```

## Phase Integration

| Phase | LLM Role |
|-------|----------|
| **0** (now) | Agent schema, credential vault, LLM gateway ports |
| **1** | Embeddings via `llm_policy.embedding` for chunk indexing |
| **3** | Reasoning Agent calls `LLMGateway.chat()` with EvidencePackets |
| **4** | Mesh nodes share gateway; per-node model overrides via agent config |

## Security

- Secrets encrypted at rest (Fernet; replace with KMS in production)
- Audit logs record credential_ref, never the secret
- Tenant/workspace isolation on credential store
- `auth_type: none` only for local Ollama (no egress)

## Migration from v2.0

v2.0 agents with `model_policy` (GPT-4, Claude) remain valid for backward compatibility. New agents should use v2.1 with `llm_policy`.
