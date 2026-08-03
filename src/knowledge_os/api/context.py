from dataclasses import dataclass
from uuid import UUID


@dataclass
class RequestContext:
    trace_id: str
    user_id: UUID | None
    email: str | None
    roles: list[str]
    tenant_id: UUID | None = None
    workspace_id: UUID | None = None

    def has_role(self, *roles: str) -> bool:
        return any(role in self.roles for role in roles)

    def require_authenticated(self) -> UUID:
        if self.user_id is None:
            raise PermissionError("Authentication required")
        return self.user_id
