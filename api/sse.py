"""Server-Sent Events manager — pushes mission lifecycle events to subscribed clients.

v0: in-process asyncio.Queue per subscriber (single-worker).
Post-v0: Redis pub/sub for multi-worker fan-out (see ADR-006).

Events emitted:
  mission.created   — new mission row inserted
  agent.started     — expert agent began running
  agent.completed   — expert agent wrote its output
  agent.failed      — expert agent raised an exception
  audit.ready       — evidence_consolidator wrote audit.md
  mission.completed — mission status updated to CLOSED or PARTIAL
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import AsyncGenerator

log = logging.getLogger(__name__)

# Maximum queued events per subscriber before oldest are dropped.
_QUEUE_MAX = 64

# Sentinel pushed to queues on unsubscribe.
_DISCONNECT = object()


class SSEManager:
    """Maintains per-mission subscriber queues and broadcasts typed events."""

    def __init__(self) -> None:
        # mission_id → list[asyncio.Queue]
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def subscribe(self, mission_id: str) -> AsyncGenerator[str, None]:
        """Yield SSE-formatted strings until the client disconnects."""
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._subscribers[mission_id].append(q)
        log.debug("SSE: new subscriber for mission %s (total %d)", mission_id, len(self._subscribers[mission_id]))
        try:
            while True:
                item = await q.get()
                if item is _DISCONNECT:
                    break
                yield item
        finally:
            try:
                self._subscribers[mission_id].remove(q)
            except ValueError:
                pass
            if not self._subscribers[mission_id]:
                del self._subscribers[mission_id]
            log.debug("SSE: subscriber removed for mission %s", mission_id)

    async def broadcast(
        self,
        mission_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """Push one event to all active subscribers for ``mission_id``."""
        payload = _format_sse(event_type, data)
        queues = list(self._subscribers.get(mission_id, []))
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                log.warning("SSE: queue full for mission %s — dropping event %s", mission_id, event_type)

    async def close_all(self, mission_id: str) -> None:
        """Signal all subscribers for a mission to disconnect."""
        for q in list(self._subscribers.get(mission_id, [])):
            try:
                q.put_nowait(_DISCONNECT)
            except asyncio.QueueFull:
                pass

    @property
    def subscriber_count(self) -> int:
        return sum(len(qs) for qs in self._subscribers.values())


def _format_sse(event_type: str, data: dict) -> str:
    """Format a Server-Sent Events message string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# Module-level singleton — imported by routes and pipeline orchestrator.
sse_manager = SSEManager()
