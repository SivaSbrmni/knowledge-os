"""Redis-backed session context store."""

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import redis.asyncio as redis


@dataclass
class SessionContext:
    session_id: UUID
    workspace_id: UUID
    agent_id: str
    messages: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class RedisSessionStore:
    def __init__(self, redis_url: str, ttl_seconds: int = 3600):
        self._redis_url = redis_url
        self._ttl = ttl_seconds
        self._client: redis.Redis | None = None

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _key(self, session_id: UUID) -> str:
        return f"kos:session:{session_id}"

    async def create(
        self, workspace_id: UUID, agent_id: str, metadata: dict | None = None
    ) -> SessionContext:
        session_id = uuid4()
        ctx = SessionContext(
            session_id=session_id,
            workspace_id=workspace_id,
            agent_id=agent_id,
            metadata=metadata or {},
        )
        await self.save(ctx)
        return ctx

    async def get(self, session_id: UUID) -> SessionContext | None:
        client = await self._get_client()
        raw = await client.get(self._key(session_id))
        if not raw:
            return None
        data = json.loads(raw)
        return SessionContext(
            session_id=UUID(data["session_id"]),
            workspace_id=UUID(data["workspace_id"]),
            agent_id=data["agent_id"],
            messages=data.get("messages", []),
            metadata=data.get("metadata", {}),
        )

    async def save(self, ctx: SessionContext) -> None:
        client = await self._get_client()
        payload = json.dumps(
            {
                "session_id": str(ctx.session_id),
                "workspace_id": str(ctx.workspace_id),
                "agent_id": ctx.agent_id,
                "messages": ctx.messages,
                "metadata": ctx.metadata,
            }
        )
        await client.setex(self._key(ctx.session_id), self._ttl, payload)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
