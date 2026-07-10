"""Event history + live fan-out.

In-memory ring of recent events, broadcast to WebSocket subscribers, and
periodically flushed to a rolling nexus_event_log .jbt (honoring the .jbt
mandate). Daily rotation and retention policy land with M4.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import jbt


class EventBus:
    def __init__(self, log_path: Path | None = None, *, ring_size: int = 1000,
                 flush_every: int = 25) -> None:
        self._ring: deque[dict[str, Any]] = deque(maxlen=ring_size)
        self._subscribers: set[asyncio.Queue] = set()
        self._log_path = log_path
        self._flush_every = flush_every
        self._since_flush = 0

    def emit(self, event_type: str, source: str, summary: str,
             payload: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "type": event_type,
            "source": source,
            "summary": summary,  # human readable — what happened, not raw JSON
            "payload": payload or {},
        }
        self._ring.append(event)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow consumer: drop rather than block the emitter
        self._since_flush += 1
        if self._log_path and self._since_flush >= self._flush_every:
            self.flush()
        return event

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._ring)[-limit:]

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def flush(self) -> None:
        if not self._log_path:
            return
        doc = jbt.new("nexus_event_log", {"events": list(self._ring)},
                      name="Nexus rolling event log")
        jbt.save(self._log_path, doc)
        self._since_flush = 0
