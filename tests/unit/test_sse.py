"""Unit tests for api/sse.py — SSEManager."""

import asyncio
import json

import pytest

from api.sse import SSEManager, _format_sse


# ── _format_sse ───────────────────────────────────────────────────────────────


def test_format_sse_structure():
    msg = _format_sse("audit.ready", {"mission_id": "M-001", "status": "ok"})
    assert msg.startswith("event: audit.ready\n")
    assert "data: " in msg
    assert msg.endswith("\n\n")
    data = json.loads(msg.split("data: ")[1].strip())
    assert data["mission_id"] == "M-001"


# ── SSEManager ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_reaches_subscriber():
    mgr = SSEManager()
    received: list[str] = []

    async def consume():
        async for event in mgr.subscribe("M-001"):
            received.append(event)
            break  # stop after first message

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)  # let subscriber register
    await mgr.broadcast("M-001", "mission.created", {"id": "M-001"})
    await asyncio.wait_for(task, timeout=1.0)

    assert len(received) == 1
    assert "mission.created" in received[0]


@pytest.mark.asyncio
async def test_broadcast_no_subscribers_silent():
    mgr = SSEManager()
    # Should not raise even with no active subscribers
    await mgr.broadcast("nonexistent", "agent.started", {"agent": "kafka-strimzi"})


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive():
    mgr = SSEManager()
    results: list[list[str]] = [[], []]

    async def consumer(idx: int):
        async for event in mgr.subscribe("M-002"):
            results[idx].append(event)
            break

    t1 = asyncio.create_task(consumer(0))
    t2 = asyncio.create_task(consumer(1))
    await asyncio.sleep(0)
    await mgr.broadcast("M-002", "audit.ready", {"mission_id": "M-002"})
    await asyncio.gather(t1, t2)

    assert len(results[0]) == 1
    assert len(results[1]) == 1


@pytest.mark.asyncio
async def test_subscriber_count():
    mgr = SSEManager()
    assert mgr.subscriber_count == 0

    ready = asyncio.Event()
    done = asyncio.Event()

    async def consumer():
        async for _ in mgr.subscribe("M-003"):
            ready.set()
            done.set()
            break

    task = asyncio.create_task(consumer())
    # Pump the event loop until the subscription is registered.
    for _ in range(10):
        await asyncio.sleep(0)
        if mgr.subscriber_count == 1:
            break
    assert mgr.subscriber_count == 1

    await mgr.broadcast("M-003", "ping", {})
    await asyncio.wait_for(done.wait(), timeout=1.0)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, StopAsyncIteration):
        pass


@pytest.mark.asyncio
async def test_close_all_disconnects_subscriber():
    mgr = SSEManager()
    events: list[str] = []

    async def consumer():
        async for event in mgr.subscribe("M-004"):
            events.append(event)

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0)
    await mgr.close_all("M-004")
    await asyncio.wait_for(task, timeout=1.0)
    assert mgr.subscriber_count == 0
