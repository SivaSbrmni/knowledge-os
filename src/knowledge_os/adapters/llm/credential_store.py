import base64
import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_os.adapters.persistence.models import ProviderCredentialModel
from knowledge_os.domain.llm import ProviderCredential
from knowledge_os.ports.llm import CredentialStore


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


class PostgresCredentialStore(CredentialStore):
    """
    Encrypts tokens at rest using Fernet keyed from platform JWT_SECRET.
    Production should use KMS/Vault — this adapter is replaceable via port.
    """

    def __init__(self, session: AsyncSession, encryption_key: str):
        self._session = session
        self._fernet = Fernet(_derive_fernet_key(encryption_key))

    def _encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Failed to decrypt credential") from exc

    def _to_domain(self, model: ProviderCredentialModel) -> ProviderCredential:
        return ProviderCredential(
            id=model.id,
            workspace_id=model.workspace_id,
            credential_ref=model.credential_ref,
            provider=model.provider,
            auth_type=model.auth_type,
            description=model.description,
            is_active=model.is_active,
            created_by=model.created_by,
        )

    async def store(
        self,
        workspace_id: UUID,
        credential_ref: str,
        provider: str,
        auth_type: str,
        secret: str,
        description: str,
        created_by: UUID | None,
    ) -> ProviderCredential:
        existing = await self.get_metadata(workspace_id, credential_ref)
        encrypted = self._encrypt(secret)
        if existing:
            await self._session.execute(
                update(ProviderCredentialModel)
                .where(
                    ProviderCredentialModel.workspace_id == workspace_id,
                    ProviderCredentialModel.credential_ref == credential_ref,
                )
                .values(
                    encrypted_secret=encrypted,
                    provider=provider,
                    auth_type=auth_type,
                    description=description,
                    is_active=True,
                )
            )
            await self._session.flush()
            result = await self.get_metadata(workspace_id, credential_ref)
            assert result is not None
            return result

        model = ProviderCredentialModel(
            id=uuid4(),
            workspace_id=workspace_id,
            credential_ref=credential_ref,
            provider=provider,
            auth_type=auth_type,
            encrypted_secret=encrypted,
            description=description,
            is_active=True,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        await self._session.flush()
        return self._to_domain(model)

    async def resolve_secret(self, workspace_id: UUID, credential_ref: str) -> str | None:
        stmt = select(ProviderCredentialModel).where(
            ProviderCredentialModel.workspace_id == workspace_id,
            ProviderCredentialModel.credential_ref == credential_ref,
            ProviderCredentialModel.is_active.is_(True),
        )
        model = await self._session.scalar(stmt)
        if model is None:
            return None
        return self._decrypt(model.encrypted_secret)

    async def get_metadata(
        self, workspace_id: UUID, credential_ref: str
    ) -> ProviderCredential | None:
        stmt = select(ProviderCredentialModel).where(
            ProviderCredentialModel.workspace_id == workspace_id,
            ProviderCredentialModel.credential_ref == credential_ref,
        )
        model = await self._session.scalar(stmt)
        return self._to_domain(model) if model else None

    async def list_credentials(self, workspace_id: UUID) -> list[ProviderCredential]:
        stmt = select(ProviderCredentialModel).where(
            ProviderCredentialModel.workspace_id == workspace_id,
            ProviderCredentialModel.is_active.is_(True),
        )
        results = await self._session.scalars(stmt)
        return [self._to_domain(r) for r in results]

    async def deactivate(self, workspace_id: UUID, credential_ref: str) -> None:
        await self._session.execute(
            update(ProviderCredentialModel)
            .where(
                ProviderCredentialModel.workspace_id == workspace_id,
                ProviderCredentialModel.credential_ref == credential_ref,
            )
            .values(is_active=False)
        )
        await self._session.flush()
