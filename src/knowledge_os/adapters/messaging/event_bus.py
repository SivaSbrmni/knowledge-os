import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import redis.asyncio as redis

from knowledge_os.domain.models import PlatformEvent
from knowledge_os.ports.repositories import EventBus

EventHandler = Callable[[PlatformEvent], Awaitable[None]]


class InMemoryEventBus(EventBus):
    """In-memory event bus for tests and local development without Redis."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self.published: list[PlatformEvent] = []

    async def publish(self, event: PlatformEvent) -> None:
        self.published.append(event)
        for handler in self._handlers.get(event.topic, []):
            await handler(event)
        for handler in self._handlers.get("*", []):
            await handler(event)

    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        self._handlers[topic].append(handler)


class RedisEventBus(EventBus):
    """Durable event bus using Redis Streams."""

    def __init__(self, redis_url: str, stream_prefix: str = "kos:events"):
        self._redis_url = redis_url
        self._stream_prefix = stream_prefix
        self._client: redis.Redis | None = None
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _stream_key(self, topic: str) -> str:
        return f"{self._stream_prefix}:{topic}"

    async def publish(self, event: PlatformEvent) -> None:
        client = await self._get_client()
        payload = {
            "event_id": str(event.event_id),
            "topic": event.topic,
            "event_type": event.event_type,
            "tenant_id": str(event.tenant_id) if event.tenant_id else "",
            "workspace_id": str(event.workspace_id) if event.workspace_id else "",
            "actor_id": str(event.actor_id) if event.actor_id else "",
            "trace_id": event.trace_id,
            "payload": json.dumps(event.payload, default=str),
            "payload_hash": event.payload_hash,
            "occurred_at": event.occurred_at.isoformat(),
            "metadata": json.dumps(event.metadata, default=str),
        }
        await client.xadd(self._stream_key(event.topic), payload)

        for handler in self._handlers.get(event.topic, []):
            await handler(event)

    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        self._handlers[topic].append(handler)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def build_platform_event(
    *,
    topic: str,
    event_type: str,
    trace_id: str,
    payload: dict[str, Any],
    tenant_id: Any = None,
    workspace_id: Any = None,
    actor_id: Any = None,
    metadata: dict[str, Any] | None = None,
) -> PlatformEvent:
    from knowledge_os.domain.utils import hash_payload

    return PlatformEvent(
        event_id=uuid4(),
        topic=topic,
        event_type=event_type,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        actor_id=actor_id,
        trace_id=trace_id,
        payload=payload,
        payload_hash=hash_payload(payload),
        occurred_at=datetime.now(UTC),
        metadata=metadata or {},
    )
