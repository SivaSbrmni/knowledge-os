# Knowledge OS

A multi-tenant **Knowledge Operating System** — the platform kernel for trustworthy AI mentors and knowledge applications.

> **Phase 1** delivers the walking skeleton: upload PDF → ask question → answer with citations and trust vector.

## Architecture

```
Platform → Organization → Workspace → Agent → Knowledge → User
```

Phase 1 adds knowledge ingestion, vector retrieval, session orchestration, and a linear query pipeline (upload → ask → cite).

### Platform Planes (Phase 0 scope)

| Plane | Components |
|-------|------------|
| **Platform Services** | Identity (JWT/OIDC-ready), Tenant Manager, Agent Registry, Audit Store |
| **Interaction Plane** | API Gateway with trace context, rate limiting stub |
| **Event Bus** | Redis Streams (durable) with in-memory fallback |

### Design Principles

- **Hexagonal architecture** — domain logic depends on ports, not adapters
- **Immutable audit** — append-only audit records with payload hashing
- **Agents as configuration** — versioned YAML/JSON validated against Agent Schema v2.0
- **Replaceable components** — swap Postgres, Redis, JWT/OIDC without domain changes
- **Tenant isolation** — organization-scoped data with workspace boundaries

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (for local development without Docker)

### Run with Docker

```bash
# Start Postgres, Redis, and API
docker compose up --build

# Run migrations (in another terminal)
docker compose exec api alembic upgrade head

# Seed demo data
docker compose exec api python scripts/seed_phase0.py
```

API available at: http://localhost:8000  
Web UI: http://localhost:8000/ui  
OpenAPI docs: http://localhost:8000/docs

### Local Development

```bash
cp .env.example .env
pip install -e ".[dev]"

# Start dependencies
docker compose up postgres redis -d

# Migrate and run
alembic upgrade head
uvicorn knowledge_os.api.app:app --reload
```

## API Overview

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness check |
| `GET /ready` | Readiness (DB + Redis) |
| `POST /api/v1/auth/dev-token` | Issue dev JWT (development only) |
| `POST /api/v1/organizations` | Create organization |
| `POST /api/v1/organizations/{id}/workspaces` | Create workspace |
| `POST /api/v1/users` | Register user |
| `POST /api/v1/workspaces/{id}/knowledge/upload` | Upload PDF/text knowledge |
| `GET /api/v1/workspaces/{id}/knowledge/assets` | List uploaded documents |
| `POST /api/v1/workspaces/{id}/sessions` | Create chat session |
| `POST /api/v1/workspaces/{id}/sessions/{sid}/query` | Ask question (returns citations + trust) |
| `POST /api/v1/workspaces/{id}/agents` | Register agent (schema v2.1) |
| `GET /api/v1/audit/trace/{trace_id}` | Query audit by trace |

All requests support `X-Trace-Id`. Authenticated requests use `Authorization: Bearer <token>`.

## Agent Schema

Agents are defined as versioned JSON/YAML configuration validated against `schemas/agent-schema-v2.0.json`. See `examples/upsc-mentor-agent.json` for the UPSC Mentor reference config.

## Project Structure

```
src/knowledge_os/
├── domain/          # Entities, enums, utilities
├── ports/           # Repository & service interfaces
├── adapters/        # Postgres, Redis, JWT implementations
├── services/        # Application services (tenant, agent registry)
├── schemas/         # Agent schema validation
└── api/             # FastAPI app, routes, middleware
```

## Tests

```bash
pytest
```

## Phase Roadmap

| Phase | Focus |
|-------|-------|
| **0** | Platform kernel — tenancy, agents, events, audit |
| **1** | Walking skeleton — upload → ask → cite |
| **2** | Knowledge fabric — immutability, graph, platform public layer |
| **3** | Inference runtime — trust pipeline, policy enforcement, reasoning agent |
| **4** (current) | Agentic mesh — independently deployable nodes |
| **5** | Enterprise — billing, compliance, HITL |
| **6** | Ecosystem — provider SDK, marketplace |

## License

Proprietary — Knowledge OS Platform
