"""Workspace-scoped authorization — DB membership first, production-strict."""

from uuid import UUID

from fastapi import HTTPException, status

from knowledge_os.config import get_settings
from knowledge_os.domain.enums import Role
from knowledge_os.ports.repositories import TenantRepository

_PRIVILEGED_JWT_ROLES = frozenset({
    Role.PLATFORM_ADMIN.value,
    Role.ORG_ADMIN.value,
    Role.WORKSPACE_ADMIN.value,
    Role.MENTOR.value,
    Role.LEARNER.value,
    Role.VIEWER.value,
})

WORKSPACE_MEMBER_ROLES = (
    Role.WORKSPACE_ADMIN.value,
    Role.MENTOR.value,
    Role.LEARNER.value,
    Role.VIEWER.value,
)

WORKSPACE_WRITE_ROLES = (
    Role.WORKSPACE_ADMIN.value,
    Role.MENTOR.value,
    Role.LEARNER.value,
)

WORKSPACE_REVIEW_ROLES = (
    Role.WORKSPACE_ADMIN.value,
    Role.MENTOR.value,
)


class AuthorizationService:
    def __init__(self, tenant_repo: TenantRepository):
        self._tenant_repo = tenant_repo

    async def assert_workspace_access(
        self,
        workspace_id: UUID,
        user_id: UUID,
        *,
        allowed_roles: tuple[str, ...],
        jwt_roles: list[str],
    ) -> str:
        membership = await self._tenant_repo.get_workspace_membership(workspace_id, user_id)
        if membership is not None:
            if membership.role in allowed_roles or membership.role == Role.WORKSPACE_ADMIN.value:
                return membership.role
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{membership.role}' cannot perform this action",
            )

        settings = get_settings()
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No workspace membership for this user",
            )

        if settings.is_development:
            if Role.PLATFORM_ADMIN.value in jwt_roles:
                return Role.PLATFORM_ADMIN.value

            for role in jwt_roles:
                if role in allowed_roles:
                    return role

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace access denied",
        )

    async def assert_session_owner(
        self,
        session_user_id: UUID | None,
        caller_id: UUID,
        jwt_roles: list[str],
    ) -> None:
        if session_user_id is None:
            return
        if session_user_id == caller_id:
            return
        settings = get_settings()
        if not settings.is_production and Role.PLATFORM_ADMIN.value in jwt_roles:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to this user",
        )
