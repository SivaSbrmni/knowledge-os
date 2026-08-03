import pytest

from knowledge_os.adapters.messaging.event_bus import InMemoryEventBus, build_platform_event
from knowledge_os.domain.enums import EventTopic
from knowledge_os.domain.utils import hash_payload, new_trace_id


@pytest.mark.asyncio
async def test_event_bus_publishes_to_handlers():
    bus = InMemoryEventBus()
    received = []

    async def handler(event):
        received.append(event)

    await bus.subscribe(EventTopic.AGENT, handler)
    event = build_platform_event(
        topic=EventTopic.AGENT,
        event_type="agent.version.created",
        trace_id=new_trace_id(),
        payload={"agent_id": "test-agent"},
    )
    await bus.publish(event)

    assert len(bus.published) == 1
    assert len(received) == 1
    assert received[0].event_type == "agent.version.created"


def test_hash_payload_is_deterministic():
    payload = {"b": 2, "a": 1}
    assert hash_payload(payload) == hash_payload({"a": 1, "b": 2})


def test_trace_id_is_uuid_format():
    trace = new_trace_id()
    assert len(trace) == 36
