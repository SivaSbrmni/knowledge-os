from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_os.adapters.auth.jwt_provider import JWTAuthProvider
from knowledge_os.adapters.llm.credential_store import PostgresCredentialStore
from knowledge_os.adapters.llm.gateway import AgentLLMGateway
from knowledge_os.adapters.messaging.event_bus import InMemoryEventBus, RedisEventBus
from knowledge_os.adapters.persistence.database import get_db_session
from knowledge_os.adapters.persistence.repositories import (
    PostgresAgentRepository,
    PostgresAuditStore,
    PostgresTenantRepository,
)
from knowledge_os.api.context import RequestContext
from knowledge_os.config import get_settings
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.ports.repositories import EventBus
from knowledge_os.schemas.agent_validator import AgentSchemaValidator
from knowledge_os.services.credentials import CredentialService
from knowledge_os.services.platform import AgentRegistryService, TenantService

_auth_provider = JWTAuthProvider()
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        settings = get_settings()
        if settings.environment in {"test", "testing"}:
            _event_bus = InMemoryEventBus()
        else:
            _event_bus = RedisEventBus(settings.redis_url)
    return _event_bus


async def get_request_context(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    x_workspace_id: Annotated[str | None, Header(alias="X-Workspace-Id")] = None,
) -> RequestContext:
    trace_id = getattr(request.state, "trace_id", None) or "unknown"
    user_id = None
    email = None
    roles: list[str] = []

    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        try:
            claims = await _auth_provider.verify_token(token)
            user_id = UUID(claims["sub"])
            email = claims.get("email")
            roles = claims.get("roles", [])
        except (ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
            ) from exc

    tenant_id = None
    workspace_id = None
    if x_tenant_id:
        try:
            tenant_id = UUID(x_tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid X-Tenant-Id") from exc
    if x_workspace_id:
        try:
            workspace_id = UUID(x_workspace_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid X-Workspace-Id") from exc

    return RequestContext(
        trace_id=trace_id,
        user_id=user_id,
        email=email,
        roles=roles,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )


def require_roles(*required_roles: str):
    async def checker(ctx: Annotated[RequestContext, Depends(get_request_context)]) -> RequestContext:
        if not ctx.has_role(*required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(required_roles)}",
            )
        return ctx

    return checker


async def get_tenant_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
) -> TenantService:
    return TenantService(
        tenant_repo=PostgresTenantRepository(session),
        audit_store=PostgresAuditStore(session),
        event_bus=event_bus,
    )


async def get_agent_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    event_bus: Annotated[EventBus, Depends(get_event_bus)],
) -> AgentRegistryService:
    return AgentRegistryService(
        agent_repo=PostgresAgentRepository(session),
        tenant_repo=PostgresTenantRepository(session),
        audit_store=PostgresAuditStore(session),
        event_bus=event_bus,
        validator=AgentSchemaValidator(),
    )


async def get_audit_store(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PostgresAuditStore:
    return PostgresAuditStore(session)


async def get_credential_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CredentialService:
    settings = get_settings()
    return CredentialService(
        credential_store=PostgresCredentialStore(session, settings.jwt_secret),
        audit_store=PostgresAuditStore(session),
    )


async def get_llm_gateway(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> LLMGateway:
    settings = get_settings()
    return AgentLLMGateway(
        credential_store=PostgresCredentialStore(session, settings.jwt_secret),
    )


def get_auth_provider() -> JWTAuthProvider:
    return _auth_provider
