# Phase 5 — Enterprise Compliance Plane

Phase 5 hardens Knowledge OS for regulated wealth-management workloads: enforced workspace authorization, immutable audit, human-in-the-loop review, usage metering, and session binding.

## Capabilities

| Area | Implementation |
|------|----------------|
| **Authorization** | `AuthorizationService` — DB membership first; JWT role fallback only in non-production |
| **Session binding** | Sessions store `user_id`; queries rejected if caller ≠ owner |
| **Audit** | Upload + query paths append `audit_records`; migration 005 adds immutability trigger |
| **HITL** | `review_queue` table + `/reviews/pending` and `/reviews/{id}/action` |
| **Metering** | `usage_events` table; hooks on upload and query |
| **Compliance API** | `compliance_router` under `/api/v1/workspaces/{id}/...` |

## Migration

```bash
alembic upgrade head
```

Revision `005` creates `review_queue`, `usage_events`, and `audit_records_immutable` trigger.

## HITL policy (agent config)

```json
"compliance_policy": {
  "enabled": true,
  "require_hitl_on_withhold": true,
  "require_hitl_below_trust": 0.75
}
```

Low-trust or withheld answers enqueue a review item. Mentors/admins approve or reject via API.

## Security notes

- Production (`ENVIRONMENT=production`) rejects workspace access without DB membership.
- Development/testing allow platform-admin JWT bypass for bootstrap flows.
- Sessions are capability tokens only when `user_id` is unset (legacy); new sessions always bind owner.

## API additions

- `GET /workspaces/{id}/reviews/pending`
- `POST /workspaces/{id}/reviews/{review_id}/action`
- `GET /workspaces/{id}/usage/summary`
- `QueryResponse.review_id` when HITL enqueued
