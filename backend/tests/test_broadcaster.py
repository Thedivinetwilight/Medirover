"""Broadcaster fan-out behavior with fake websockets."""

from __future__ import annotations

from backend.services.broadcaster import Broadcaster
from shared.events import Event
from shared.types import Severity


class FakeWS:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[str] = []
        self.closed: list[int] = []
        self.fail = fail

    async def send_text(self, text: str) -> None:
        if self.fail:
            raise ConnectionError("gone")
        self.sent.append(text)

    async def close(self, code: int = 1000) -> None:
        self.closed.append(code)


async def test_filtering_and_broadcast():
    b = Broadcaster()
    all_client = FakeWS()
    filtered = FakeWS()
    b.register(all_client)
    b.register(filtered, node_ids={"nodeA"})

    await b.publish_state_update("nodeA", {"connectivity": "ONLINE"})
    await b.publish_state_update("nodeB", {"connectivity": "OFFLINE"})
    assert len(all_client.sent) == 2
    assert len(filtered.sent) == 1  # only nodeA matched the filter

    event = Event.create(
        "NODE_IDENTIFIED", source="test", node_id="nodeB", message="x", severity=Severity.INFO
    )
    await b.publish_event(event)
    assert len(all_client.sent) == 3
    assert len(filtered.sent) == 1  # nodeB does not match filter {nodeA}


async def test_dead_client_is_dropped():
    b = Broadcaster()
    dead = FakeWS(fail=True)
    alive = FakeWS()
    b.register(dead)
    b.register(alive)

    await b.publish_state_update("nodeA", {"connectivity": "ONLINE"})
    assert len(b) == 1  # dead client removed
    assert len(alive.sent) == 1


async def test_bad_frame_limit_tracking():
    b = Broadcaster()
    ws = FakeWS()
    b.register(ws)
    assert b.mark_bad_frame(ws) == 1
    assert b.mark_bad_frame(ws) == 2


async def test_close_all():
    b = Broadcaster()
    ws = FakeWS()
    b.register(ws)
    await b.close_all()
    assert ws.closed == [1001]
    assert len(b) == 0
