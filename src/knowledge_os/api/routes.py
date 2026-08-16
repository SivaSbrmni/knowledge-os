from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_os.adapters.persistence.database import get_db_session
from knowledge_os.adapters.persistence.repositories import PostgresTenantRepository
from knowledge_os.api.context import RequestContext
from knowledge_os.api.dependencies import (
    get_agent_service,
    get_audit_store,
    get_auth_provider,
    get_credential_service,
    get_llm_gateway,
    get_request_context,
    get_tenant_service,
    require_roles,
    require_workspace_access,
)
from knowledge_os.api.schemas import (
    AgentRegisterRequest,
    AgentVersionResponse,
    AuditRecordResponse,
    CredentialCreate,
    CredentialResponse,
    DevTokenRequest,
    DevTokenResponse,
    LLMPolicyValidateResponse,
    OrganizationCreate,
    OrganizationResponse,
    UserCreate,
    UserResponse,
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceMemberResponse,
    WorkspaceResponse,
)
from knowledge_os.config import get_settings
from knowledge_os.domain.enums import Role
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.schemas.agent_validator import AgentSchemaValidationError
from knowledge_os.schemas.llm_policy import parse_llm_policy
from knowledge_os.services.authorization import WORKSPACE_WRITE_ROLES
from knowledge_os.services.credentials import CredentialService
from knowledge_os.services.platform import AgentRegistryService, TenantService

router = APIRouter()


@router.post("/auth/dev-token", response_model=DevTokenResponse)
async def issue_dev_token(
    body: DevTokenRequest,
    service: Annotated[TenantService, Depends(get_tenant_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    auth=Depends(get_auth_provider),
):
    settings = get_settings()
    if not settings.is_development:
        raise HTTPException(status_code=404, detail="Not found")
    await service.ensure_user(body.user_id, body.email)
    await session.commit()
    token = await auth.issue_dev_token(body.user_id, body.email, body.roles)
    return DevTokenResponse(access_token=token)


@router.post("/organizations", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    body: OrganizationCreate,
    ctx: Annotated[RequestContext, Depends(require_roles(Role.PLATFORM_ADMIN.value))],
    service: Annotated[TenantService, Depends(get_tenant_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    existing = await PostgresTenantRepository(session).get_organization_by_slug(body.slug)
    if existing:
        raise HTTPException(status_code=409, detail="Organization slug already exists")
    org = await service.create_organization(body.name, body.slug, actor_id=ctx.user_id, trace_id=ctx.trace_id)
    await session.commit()
    return OrganizationResponse.model_validate(org)


@router.get("/organizations/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: UUID,
    ctx: Annotated[RequestContext, Depends(get_request_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    ctx.require_authenticated()
    org = await PostgresTenantRepository(session).get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationResponse.model_validate(org)


@router.post(
    "/organizations/{org_id}/workspaces",
    response_model=WorkspaceResponse,
    status_code=201,
)
async def create_workspace(
    org_id: UUID,
    body: WorkspaceCreate,
    ctx: Annotated[RequestContext, Depends(require_roles(Role.ORG_ADMIN.value, Role.PLATFORM_ADMIN.value))],
    service: Annotated[TenantService, Depends(get_tenant_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    org = await PostgresTenantRepository(session).get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    workspace = await service.create_workspace(
        org_id, body.name, body.slug, actor_id=ctx.user_id, trace_id=ctx.trace_id
    )
    await session.commit()
    return WorkspaceResponse.model_validate(workspace)


@router.get("/organizations/{org_id}/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces(
    org_id: UUID,
    ctx: Annotated[RequestContext, Depends(get_request_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    ctx.require_authenticated()
    workspaces = await PostgresTenantRepository(session).list_workspaces(org_id)
    return [WorkspaceResponse.model_validate(w) for w in workspaces]


@router.post("/users", response_model=UserResponse, status_code=201)
async def register_user(
    body: UserCreate,
    ctx: Annotated[RequestContext, Depends(get_request_context)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    user = await service.register_user(body.email, body.display_name, actor_id=ctx.user_id, trace_id=ctx.trace_id)
    await session.commit()
    return UserResponse.model_validate(user)


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=201,
)
async def add_workspace_member(
    workspace_id: UUID,
    body: WorkspaceMemberCreate,
    ctx: Annotated[
        RequestContext,
        Depends(require_workspace_access(Role.WORKSPACE_ADMIN.value, Role.ORG_ADMIN.value)),
    ],
    service: Annotated[TenantService, Depends(get_tenant_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        membership = await service.add_workspace_member(
            workspace_id, body.user_id, body.role, actor_id=ctx.user_id, trace_id=ctx.trace_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return WorkspaceMemberResponse.model_validate(membership)


@router.post(
    "/workspaces/{workspace_id}/agents",
    response_model=AgentVersionResponse,
    status_code=201,
)
async def register_agent(
    workspace_id: UUID,
    body: AgentRegisterRequest,
    ctx: Annotated[RequestContext, Depends(require_workspace_access(*WORKSPACE_WRITE_ROLES))],
    service: Annotated[AgentRegistryService, Depends(get_agent_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    config = {**body.config, "workspace_id": str(workspace_id)}
    try:
        version = await service.register_agent(
            config, actor_id=ctx.user_id, trace_id=ctx.trace_id, activate=body.activate
        )
    except AgentSchemaValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.commit()
    return AgentVersionResponse.model_validate(version)


@router.get("/workspaces/{workspace_id}/agents/{agent_id}", response_model=AgentVersionResponse)
async def get_active_agent(
    workspace_id: UUID,
    agent_id: str,
    ctx: Annotated[RequestContext, Depends(require_workspace_access())],
    service: Annotated[AgentRegistryService, Depends(get_agent_service)],
):
    ctx.require_authenticated()
    version = await service.get_active_agent(agent_id, workspace_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Active agent version not found")
    return AgentVersionResponse.model_validate(version)


@router.get(
    "/workspaces/{workspace_id}/agents/{agent_id}/versions",
    response_model=list[AgentVersionResponse],
)
async def list_agent_versions(
    workspace_id: UUID,
    agent_id: str,
    ctx: Annotated[RequestContext, Depends(require_workspace_access())],
    service: Annotated[AgentRegistryService, Depends(get_agent_service)],
):
    ctx.require_authenticated()
    versions = await service.list_versions(agent_id, workspace_id)
    return [AgentVersionResponse.model_validate(v) for v in versions]


@router.post(
    "/workspaces/{workspace_id}/agents/{agent_id}/versions/{version}/activate",
    response_model=AgentVersionResponse,
)
async def activate_agent_version(
    workspace_id: UUID,
    agent_id: str,
    version: int,
    ctx: Annotated[
        RequestContext,
        Depends(require_workspace_access(Role.WORKSPACE_ADMIN.value)),
    ],
    service: Annotated[AgentRegistryService, Depends(get_agent_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    try:
        activated = await service.activate_version(
            agent_id, workspace_id, version, actor_id=ctx.user_id, trace_id=ctx.trace_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return AgentVersionResponse.model_validate(activated)


@router.get("/audit/trace/{trace_id}", response_model=list[AuditRecordResponse])
async def get_audit_by_trace(
    trace_id: str,
    ctx: Annotated[RequestContext, Depends(require_roles(Role.WORKSPACE_ADMIN.value, Role.ORG_ADMIN.value))],
    audit_store=Depends(get_audit_store),
):
    records = await audit_store.query_by_trace(trace_id)
    return [AuditRecordResponse.model_validate(r) for r in records]


@router.get("/audit/tenant/{tenant_id}", response_model=list[AuditRecordResponse])
async def get_audit_by_tenant(
    tenant_id: UUID,
    ctx: Annotated[RequestContext, Depends(require_roles(Role.ORG_ADMIN.value, Role.PLATFORM_ADMIN.value))],
    audit_store=Depends(get_audit_store),
    limit: int = 100,
    offset: int = 0,
):
    records = await audit_store.query_by_tenant(tenant_id, limit=limit, offset=offset)
    return [AuditRecordResponse.model_validate(r) for r in records]


@router.post(
    "/workspaces/{workspace_id}/credentials",
    response_model=CredentialResponse,
    status_code=201,
)
async def store_credential(
    workspace_id: UUID,
    body: CredentialCreate,
    ctx: Annotated[
        RequestContext,
        Depends(require_workspace_access(Role.WORKSPACE_ADMIN.value)),
    ],
    service: Annotated[CredentialService, Depends(get_credential_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    workspace = await PostgresTenantRepository(session).get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    cred = await service.store_credential(
        workspace_id,
        body.credential_ref,
        body.provider,
        body.auth_type,
        body.secret,
        body.description,
        actor_id=ctx.user_id,
        trace_id=ctx.trace_id,
        tenant_id=workspace.organization_id,
    )
    await session.commit()
    return CredentialResponse(
        id=cred.id,
        workspace_id=cred.workspace_id,
        credential_ref=cred.credential_ref,
        provider=cred.provider,
        auth_type=cred.auth_type,
        description=cred.description,
        is_active=cred.is_active,
        created_by=cred.created_by,
    )


@router.get(
    "/workspaces/{workspace_id}/credentials",
    response_model=list[CredentialResponse],
)
async def list_credentials(
    workspace_id: UUID,
    ctx: Annotated[
        RequestContext,
        Depends(require_workspace_access(Role.WORKSPACE_ADMIN.value)),
    ],
    service: Annotated[CredentialService, Depends(get_credential_service)],
):
    creds = await service.list_credentials(workspace_id)
    return [
        CredentialResponse(
            id=c.id,
            workspace_id=c.workspace_id,
            credential_ref=c.credential_ref,
            provider=c.provider,
            auth_type=c.auth_type,
            description=c.description,
            is_active=c.is_active,
            created_by=c.created_by,
        )
        for c in creds
    ]


@router.post(
    "/workspaces/{workspace_id}/agents/validate-llm-policy",
    response_model=LLMPolicyValidateResponse,
)
async def validate_llm_policy(
    workspace_id: UUID,
    body: AgentRegisterRequest,
    ctx: Annotated[RequestContext, Depends(require_workspace_access(*WORKSPACE_WRITE_ROLES))],
    gateway: Annotated[LLMGateway, Depends(get_llm_gateway)],
):
    config = {**body.config, "workspace_id": str(workspace_id)}
    try:
        from knowledge_os.schemas.agent_validator import AgentSchemaValidator

        validated = AgentSchemaValidator().validate(config)
        if validated.get("schema_version") != "2.1":
            return LLMPolicyValidateResponse(valid=False, errors=["llm_policy requires schema_version 2.1"])
        policy = parse_llm_policy(validated)
        errors = await gateway.validate_policy(policy, workspace_id)
        return LLMPolicyValidateResponse(valid=len(errors) == 0, errors=errors)
    except AgentSchemaValidationError as exc:
        return LLMPolicyValidateResponse(valid=False, errors=exc.errors)
    except ValueError as exc:
        return LLMPolicyValidateResponse(valid=False, errors=[str(exc)])
