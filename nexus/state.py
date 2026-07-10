"""Last-known device state, with provenance.

Every value records where it came from (command_ack, query, probe, inferred,
manual) and when. A command being *sent* never updates state — only a parsed
acknowledgment or an explicit query does.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

VALID_SOURCES = {"command_ack", "query", "probe", "inferred", "manual"}


class StateStore:
    def __init__(self) -> None:
        self._devices: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    def update(self, device_id: str, values: dict[str, Any], source: str) -> None:
        if not values:
            return
        if source not in VALID_SOURCES:
            raise ValueError(f"unknown state source: {source}")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for key, value in values.items():
            self._devices[device_id][key] = {
                "value": value, "source": source, "updated_at": stamp}

    def snapshot(self, device_id: str) -> dict[str, dict[str, Any]]:
        return dict(self._devices.get(device_id, {}))
