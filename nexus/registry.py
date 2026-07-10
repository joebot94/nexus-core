"""Canonical device registry.

Loads `device_registry.jbt` (jbt_type: nexus_device_registry), builds one
adapter per enabled device, and tracks online/offline status. Bootstraps a
default registry on first run so `python -m nexus` works with zero setup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import jbt
from .adapters import ADAPTER_TYPES, DeviceAdapter
from .config import Settings
from .transports import SimTransport, TCPTransport

# Status vocabulary: unknown (never probed), online, offline, degraded.
DEFAULT_DEVICES: list[dict[str, Any]] = [
    {
        "device_id": "device.mgp.1",
        "type": "mgp464",
        "label": "MGP 464 Pro DI",
        "host": "10.0.0.63",
        "port": 23,
        "location": "Rack 2",
        "notes": "The live unit — `2*NN.` preset recall verified July 2026. Slots 48-71 = saved 2x2 chaos layouts, 48 = clean.",
        "enabled": True,
        "simulate": False,
    },
    {
        "device_id": "device.mgp.sim",
        "type": "mgp464",
        "label": "MGP 464 (simulated)",
        "host": "sim",
        "port": 23,
        "location": "Nowhere",
        "notes": "Simulation-mode demo device. Same adapter and API path as real hardware.",
        "enabled": True,
        "simulate": True,
    },
]


class DeviceConfig(BaseModel):
    device_id: str
    type: str
    label: str = ""
    host: str = ""
    port: int = 23
    location: str = ""
    notes: str = ""
    enabled: bool = True
    simulate: bool = False


@dataclass
class DeviceEntry:
    config: DeviceConfig
    adapter: DeviceAdapter
    status: str = "unknown"
    last_seen: str | None = None
    simulated: bool = False

    def mark(self, ok: bool) -> None:
        self.status = "online" if ok else "offline"
        if ok:
            self.last_seen = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Registry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._entries: dict[str, DeviceEntry] = {}
        self.load()

    def load(self) -> None:
        path = self.settings.registry_path
        if not path.exists():
            doc = jbt.new("nexus_device_registry", {"devices": DEFAULT_DEVICES},
                          name="Joebot Studio Device Registry")
            jbt.save(path, doc)
        doc = jbt.load(path)
        self._entries.clear()
        for raw in doc["payload"].get("devices", []):
            config = DeviceConfig(**raw)
            adapter_cls = ADAPTER_TYPES.get(config.type)
            if adapter_cls is None:
                continue  # unknown device types are skipped gracefully, .jbt style
            simulated = config.simulate or self.settings.simulate_all
            if simulated:
                transport = SimTransport(adapter_cls.Simulator())
            else:
                transport = TCPTransport(config.host, config.port)
            adapter = adapter_cls(config, transport)
            self._entries[config.device_id] = DeviceEntry(
                config=config, adapter=adapter, simulated=simulated)

    def get(self, device_id: str) -> DeviceEntry | None:
        return self._entries.get(device_id)

    def all(self) -> list[DeviceEntry]:
        return list(self._entries.values())
