from datetime import UTC, datetime
from uuid import UUID, uuid4

from knowledge_os.domain.llm import ProviderCredential
from knowledge_os.domain.models import AuditRecord
from knowledge_os.domain.utils import hash_payload, new_trace_id
from knowledge_os.ports.llm import CredentialStore
from knowledge_os.ports.repositories import AuditStore


class CredentialService:
    """Manages workspace-scoped LLM provider tokens (API keys, PATs)."""

    def __init__(self, credential_store: CredentialStore, audit_store: AuditStore):
        self._store = credential_store
        self._audit_store = audit_store

    async def store_credential(
        self,
        workspace_id: UUID,
        credential_ref: str,
        provider: str,
        auth_type: str,
        secret: str,
        description: str,
        *,
        actor_id: UUID | None = None,
        trace_id: str | None = None,
        tenant_id: UUID | None = None,
    ) -> ProviderCredential:
        trace_id = trace_id or new_trace_id()
        cred = await self._store.store(
            workspace_id=workspace_id,
            credential_ref=credential_ref,
            provider=provider,
            auth_type=auth_type,
            secret=secret,
            description=description,
            created_by=actor_id,
        )
        await self._audit_store.append(
            AuditRecord(
                id=uuid4(),
                trace_id=trace_id,
                actor_id=actor_id,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                action="credential.stored",
                resource_type="provider_credential",
                resource_id=credential_ref,
                payload_hash=hash_payload(
                    {"credential_ref": credential_ref, "provider": provider, "auth_type": auth_type}
                ),
                details={"credential_ref": credential_ref, "provider": provider},
                created_at=datetime.now(UTC),
            )
        )
        return cred

    async def list_credentials(self, workspace_id: UUID) -> list[ProviderCredential]:
        return await self._store.list_credentials(workspace_id)

    async def deactivate(self, workspace_id: UUID, credential_ref: str, **audit_kwargs) -> None:
        await self._store.deactivate(workspace_id, credential_ref)
