# Production Deployment

Regulated wealth-management deployments must satisfy these requirements before go-live.

## Required environment variables

| Variable | Production value |
|----------|------------------|
| `ENVIRONMENT` | `production` |
| `JWT_SECRET` | Strong random string (minimum 32 characters) |
| `USE_DEV_EMBEDDINGS` | `false` |
| `DATABASE_URL` | Managed Postgres with TLS |
| `REDIS_URL` | Managed Redis with TLS |

## Startup validation

The API refuses to boot in `production` when:

- `JWT_SECRET` is a known default or shorter than 32 characters
- `USE_DEV_EMBEDDINGS` is `true`

## Security controls (Phase 5+)

- Workspace authorization via DB membership (no JWT role bypass in production)
- Session binding to authenticated user
- Immutable audit trail (`audit_records` trigger)
- HITL maker-checker with `block_until_review`
- Redis-backed rate limiting in production
- Security headers (CSP, HSTS, frame denial)

## Verification before release

```bash
alembic upgrade head
python3 scripts/ensure_platform_workspace.py
python3 -m pytest tests/ -q
PYTHONPATH=src python3 scripts/verify_e2e.py
```

All tests and the verification script must pass with zero failures.
