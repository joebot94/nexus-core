"""Warm, in-memory read cache for client-facing hardware snapshots.

This is intentionally disposable: the device and Joebot Lab remain the
authority. The cache makes a newly opened control surface feel immediate while
the background task keeps a recent, bounded snapshot warm.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CachedValue:
    value: Any
    updated_at: float


class ReadCache:
    def __init__(self) -> None:
        self.telemetry: dict[str, CachedValue] = {}
        self.routes: dict[str, CachedValue] = {}
        self.names: dict[tuple[str, str], CachedValue] = {}

    @staticmethod
    def _put(store: dict, key: Any, value: Any) -> None:
        store[key] = CachedValue(value=value, updated_at=time.time())

    def put_telemetry(self, device_id: str, value: dict[str, Any]) -> None:
        self._put(self.telemetry, device_id, value)

    def put_routes(self, device_id: str, ties: dict[int, int]) -> None:
        self._put(self.routes, device_id, ties)

    def put_names(self, device_id: str, kind: str, names: dict[str, str]) -> None:
        current = dict(self.names.get((device_id, kind), CachedValue({}, 0)).value)
        current.update(names)
        self._put(self.names, (device_id, kind), current)

    @staticmethod
    def age_seconds(value: CachedValue | None) -> int | None:
        return None if value is None else max(0, int(time.time() - value.updated_at))
