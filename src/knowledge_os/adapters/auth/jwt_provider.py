from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from knowledge_os.config import get_settings
from knowledge_os.ports.repositories import AuthProvider


class JWTAuthProvider(AuthProvider):
    """
    Development JWT auth provider with OIDC-compatible claim structure.
    Replace with OIDC adapter (Auth0, Keycloak) in production.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def verify_token(self, token: str) -> dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[self._settings.jwt_algorithm],
            )
            return payload
        except JWTError as exc:
            raise ValueError("Invalid or expired token") from exc

    async def issue_dev_token(
        self, user_id: UUID, email: str, roles: list[str]
    ) -> str:
        if not self._settings.is_development:
            raise PermissionError("Dev token issuance is only allowed in development")

        now = datetime.now(UTC)
        expires = now + timedelta(minutes=self._settings.jwt_expiry_minutes)
        claims = {
            "sub": str(user_id),
            "email": email,
            "roles": roles,
            "iss": "knowledge-os-dev",
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
        }
        return jwt.encode(claims, self._settings.jwt_secret, algorithm=self._settings.jwt_algorithm)
