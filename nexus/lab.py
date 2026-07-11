"""Read-only bridge to the existing Joebot Lab dashboard.

Joebot Lab already owns the rack polling cadence and the model-specific status
queries on port 8080. Nexus consumes its public JSON rather than opening a
second poller against the same devices. This module deliberately has no action
or write path.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


class LabTelemetryError(RuntimeError):
    pass


# Current Lab status IDs. Registry entries may override with lab_device_id.
# They are used only after an operator enables the optional Lab provider.
DEFAULT_LAB_IDS = {
    "matrix12800": "mx",
    "dms3600": "dms",
    "smx": "smx",
}


def _presence(raw_state: str) -> str:
    """Translate Lab's visual dot vocabulary into explicit client semantics.

    This applies only to a signal dot on a presence-aware board. A missing
    `signals` list means unsupported/unknown, never "no signal".
    """
    return {
        "ok": "present",
        "gray": "absent",
        "warn": "degraded",
        "bad": "absent",
    }.get(raw_state, "unknown")


def normalize_device(record: dict[str, Any]) -> dict[str, Any]:
    """Reduce Lab's rich UI payload to a stable Nexus telemetry contract."""
    boards: list[dict[str, Any]] = []
    for board in record.get("boards", []) or []:
        signals = []
        for signal in board.get("signals", []) or []:
            raw_state = str(signal.get("state", ""))
            signals.append({
                "channel": str(signal.get("label", "")),
                "presence": _presence(raw_state),
                "lab_state": raw_state,
            })
        boards.append({
            "slot": board.get("slot"),
            "plane": str(board.get("plane", "")),
            "label": str(board.get("label", "")),
            "audio": bool(board.get("audio", False)),
            "port_count": board.get("port_count"),
            "signals": signals,
        })

    # Conventional DMS/Matrix-style devices publish one flat `signals` list
    # rather than modular card boards. Normalize that as one logical all-signal
    # plane so clients use the same input-presence code for both families.
    # Do not manufacture this board when the list is absent: no sensor data is
    # still unknown/unsupported, never an automatic red failure.
    if not boards and isinstance(record.get("signals"), list):
        signals = []
        for signal in record["signals"]:
            raw_state = str(signal.get("state", ""))
            signals.append({
                "channel": str(signal.get("label", "")),
                "presence": _presence(raw_state),
                "lab_state": raw_state,
            })
        boards.append({
            "slot": None,
            "plane": "all",
            "label": "Matrix inputs",
            "audio": False,
            "port_count": len(signals),
            "signals": signals,
        })

    details = record.get("details", []) or []
    # Recent Lab versions use detail rows; older versions used a dict. Keep the
    # original shape available so an older NAS image is still useful.
    return {
        "source": "joebot_lab",
        "status": record.get("status", "unknown"),
        "online": bool(record.get("online", False)),
        "summary": record.get("summary", ""),
        "last_seen_ago": record.get("last_seen_ago"),
        "details": details,
        "boards": boards,
        "raw_available": bool(record.get("raw")),
        "history": record.get("history", []) or [],
    }


class LabTelemetryClient:
    def __init__(self, base_url: str, timeout: float = 4.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def device(self, lab_device_id: str) -> dict[str, Any]:
        if not self.base_url:
            raise LabTelemetryError("Joebot Lab bridge is disabled")
        try:
            payload = await asyncio.to_thread(self._status_document)
        except (URLError, OSError, json.JSONDecodeError) as exc:
            raise LabTelemetryError(f"Joebot Lab unavailable: {exc}") from exc

        devices = payload.get("devices", {})
        if isinstance(devices, dict):
            record = devices.get(lab_device_id)
        else:
            record = next((d for d in devices if d.get("id") == lab_device_id), None)
        if not isinstance(record, dict):
            raise LabTelemetryError(f"Joebot Lab has no device '{lab_device_id}'")
        return normalize_device(record)

    def _status_document(self) -> dict[str, Any]:
        with urlopen(f"{self.base_url}/api/status", timeout=self.timeout) as response:  # nosec B310 -- configured local lab URL
            return json.loads(response.read().decode("utf-8"))
