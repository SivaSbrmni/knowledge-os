"""Shared audit append helper for compliance plane."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from knowledge_os.domain.models import AuditRecord
from knowledge_os.domain.utils import hash_payload
from knowledge_os.ports.repositories import AuditStore


async def append_audit(
    audit_store: AuditStore,
    *,
    trace_id: str,
    actor_id: UUID | None,
    tenant_id: UUID | None,
    workspace_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    details: dict,
) -> AuditRecord:
    record = AuditRecord(
        id=uuid4(),
        trace_id=trace_id,
        actor_id=actor_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        payload_hash=hash_payload(details),
        details=details,
        created_at=datetime.now(UTC),
    )
    return await audit_store.append(record)
