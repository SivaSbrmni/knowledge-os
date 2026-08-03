from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_os.adapters.persistence.database import get_db_session
from knowledge_os.api.context import RequestContext
from knowledge_os.api.dependencies import (
    get_agent_service,
    get_ingestion_service,
    get_orchestrator,
    get_request_context,
    require_roles,
)
from knowledge_os.api.knowledge_schemas import (
    CitationResponse,
    KnowledgeAssetResponse,
    QueryRequest,
    QueryResponse,
    SessionCreateRequest,
    SessionResponse,
    TrustVectorResponse,
)
from knowledge_os.domain.enums import Role
from knowledge_os.services.ingestion import IngestionService
from knowledge_os.services.orchestrator import SessionOrchestrator
from knowledge_os.services.platform import AgentRegistryService

knowledge_router = APIRouter(tags=["knowledge"])
chat_router = APIRouter(tags=["chat"])


@knowledge_router.post(
    "/workspaces/{workspace_id}/knowledge/upload",
    response_model=KnowledgeAssetResponse,
    status_code=201,
)
async def upload_knowledge(
    workspace_id: UUID,
    ctx: Annotated[RequestContext, Depends(require_roles(
        Role.WORKSPACE_ADMIN.value, Role.MENTOR.value, Role.LEARNER.value
    ))],
    ingestion: Annotated[IngestionService, Depends(get_ingestion_service)],
    agent_service: Annotated[AgentRegistryService, Depends(get_agent_service)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: UploadFile = File(...),
    agent_id: str = Form(default="upsc-mentor-v1"),
):
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")

    mime = file.content_type or "application/octet-stream"
    agent_config = None
    version = await agent_service.get_active_agent(agent_id, workspace_id)
    if version:
        agent_config = version.config

    try:
        asset = await ingestion.ingest_upload(
            workspace_id=workspace_id,
            filename=file.filename or "upload",
            content=content,
            mime_type=mime,
            agent_config=agent_config,
            trace_id=ctx.trace_id,
            actor_id=ctx.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await session.commit()
    return KnowledgeAssetResponse.model_validate(asset)


@knowledge_router.get(
    "/workspaces/{workspace_id}/knowledge/assets",
    response_model=list[KnowledgeAssetResponse],
)
async def list_knowledge_assets(
    workspace_id: UUID,
    ctx: Annotated[RequestContext, Depends(get_request_context)],
    ingestion: Annotated[IngestionService, Depends(get_ingestion_service)],
):
    ctx.require_authenticated()
    assets = await ingestion.list_assets(workspace_id)
    return [KnowledgeAssetResponse.model_validate(a) for a in assets]


@chat_router.post(
    "/workspaces/{workspace_id}/sessions",
    response_model=SessionResponse,
    status_code=201,
)
async def create_session(
    workspace_id: UUID,
    body: SessionCreateRequest,
    ctx: Annotated[RequestContext, Depends(get_request_context)],
    orchestrator: Annotated[SessionOrchestrator, Depends(get_orchestrator)],
):
    ctx.require_authenticated()
    try:
        session_ctx = await orchestrator.create_session(workspace_id, body.agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SessionResponse(
        session_id=session_ctx.session_id,
        workspace_id=session_ctx.workspace_id,
        agent_id=session_ctx.agent_id,
    )


@chat_router.post(
    "/workspaces/{workspace_id}/sessions/{session_id}/query",
    response_model=QueryResponse,
)
async def query_session(
    workspace_id: UUID,
    session_id: UUID,
    body: QueryRequest,
    ctx: Annotated[RequestContext, Depends(get_request_context)],
    orchestrator: Annotated[SessionOrchestrator, Depends(get_orchestrator)],
):
    ctx.require_authenticated()
    try:
        session_ctx, response = await orchestrator.query(session_id, body.question)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if session_ctx.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Session workspace mismatch")

    return QueryResponse(
        answer=response.answer,
        withheld=response.withheld,
        trust=TrustVectorResponse(
            source_trust=response.trust.source_trust,
            retrieval_trust=response.trust.retrieval_trust,
            reasoning_trust=response.trust.reasoning_trust,
            groundedness=response.trust.groundedness,
            overall=response.trust.overall,
            threshold_met=response.trust.threshold_met,
            explanation=response.trust.explanation,
        ),
        citations=[
            CitationResponse(**c) for c in response.citations
        ],
        evidence_count=len(response.evidence_packets),
        session_id=session_id,
    )
