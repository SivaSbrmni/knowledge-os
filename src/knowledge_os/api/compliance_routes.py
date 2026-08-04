"""Phase 5 — HITL review queue and usage metering API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_os.adapters.persistence.database import get_db_session
from knowledge_os.api.context import RequestContext
from knowledge_os.api.dependencies import (
    get_audit_store,
    get_hitl_service,
    get_usage_metering_service,
    require_workspace_access,
)
from knowledge_os.adapters.persistence.repositories import PostgresAuditStore
from knowledge_os.services.audit_helper import append_audit
from knowledge_os.api.knowledge_schemas import (
    ReviewActionRequest,
    ReviewQueueItemResponse,
    UsageSummaryResponse,
)
from knowledge_os.services.authorization import WORKSPACE_REVIEW_ROLES
from knowledge_os.services.hitl import HITLService
from knowledge_os.services.usage_metering import UsageMeteringService

compliance_router = APIRouter(tags=["compliance"])


@compliance_router.get(
    "/workspaces/{workspace_id}/reviews/pending",
    response_model=list[ReviewQueueItemResponse],
)
async def list_pending_reviews(
    workspace_id: UUID,
    ctx: Annotated[RequestContext, Depends(require_workspace_access(*WORKSPACE_REVIEW_ROLES))],
    hitl: Annotated[HITLService, Depends(get_hitl_service)],
):
    items = await hitl.list_pending(workspace_id)
    return [ReviewQueueItemResponse.model_validate(item) for item in items]


@compliance_router.post(
    "/workspaces/{workspace_id}/reviews/{review_id}/action",
    response_model=ReviewQueueItemResponse,
)
async def review_item(
    workspace_id: UUID,
    review_id: UUID,
    body: ReviewActionRequest,
    ctx: Annotated[RequestContext, Depends(require_workspace_access(*WORKSPACE_REVIEW_ROLES))],
    hitl: Annotated[HITLService, Depends(get_hitl_service)],
    audit_store: Annotated[PostgresAuditStore, Depends(get_audit_store)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    if body.status not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="status must be approved or rejected")

    user_id = ctx.require_authenticated()
    try:
        model = await hitl.review(review_id, workspace_id, user_id, body.status, body.notes)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if model is None:
        raise HTTPException(status_code=404, detail="Review item not found")

    await append_audit(
        audit_store,
        trace_id=ctx.trace_id,
        actor_id=user_id,
        tenant_id=ctx.tenant_id,
        workspace_id=workspace_id,
        action=f"compliance.review.{body.status}",
        resource_type="review_queue",
        resource_id=str(review_id),
        details={"reviewer_notes": body.notes, "requester_id": str(model.requester_id)},
    )
    await session.commit()
    return ReviewQueueItemResponse.model_validate(model)


@compliance_router.get(
    "/workspaces/{workspace_id}/usage/summary",
    response_model=UsageSummaryResponse,
)
async def usage_summary(
    workspace_id: UUID,
    ctx: Annotated[RequestContext, Depends(require_workspace_access())],
    metering: Annotated[UsageMeteringService, Depends(get_usage_metering_service)],
    event_type: str | None = None,
):
    total = await metering.sum_for_workspace(workspace_id, event_type)
    return UsageSummaryResponse(workspace_id=workspace_id, event_type=event_type, total_units=total)
