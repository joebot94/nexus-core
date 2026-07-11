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
        "device_id": "device.matrix.main",
        "type": "matrix12800",
        "label": "Matrix 12800",
        "host": "10.0.0.12",
        "port": 23,
        "location": "Rack 1",
        "password": "admin",
        "notes": "128x128. Wire syntax from deployed joebot-lab matrix12800_control.py. "
                 "May prompt for a password on connect.",
        "enabled": True,
        "simulate": False,
        "lab_device_id": "mx",
    },
    {
        "device_id": "device.dms.main",
        "type": "dms3600",
        "label": "DMS 3600",
        "host": "10.0.0.13",
        "port": 23,
        "location": "Rack 1",
        "notes": "36x36 installed card population. Wire syntax from deployed joebot-lab dms_control.py. "
                 "Primary PSU unplugged — runs on redundant (degraded is normal).",
        "enabled": True,
        "simulate": False,
        "lab_device_id": "dms",
    },
    {
        "device_id": "device.smx.main",
        "type": "smx",
        "label": "SMX System Matrix",
        "host": "10.0.0.11",
        "port": 23,
        "location": "Rack 1",
        "notes": "16x16, four planes (00 VGA / 01 S-Video / 02 Video / 04 Audio). "
                 "Preset recall is RprNN, NOT the universal N. — verified via joebot-lab. "
                 "Was unreachable on the LAN as of early July 2026.",
        "enabled": True,
        "simulate": False,
        "lab_device_id": "smx",
    },
    {
        "device_id": "device.mtpx.1",
        "type": "mtpx",
        "label": "MTPX Plus 1616",
        "host": "10.0.0.15",
        "port": 23,
        "location": "Rack 1",
        "notes": "RGB skew unit — W{in}*{r}*{g}*{b}Iseq (verified via MTPXControl). "
                 "IP UNCONFIRMED: NAS device list says .15, GlitchBoard has also seen "
                 ".61/.172/.173. Powered off as of early July 2026 — confirm IP + power "
                 "when firing skew. NAS API (status.joe.bot:8080) is a fallback route.",
        "enabled": True,
        "simulate": False,
    },
    {
        "device_id": "device.mtpx.2",
        "type": "mtpx",
        "label": "MTPX Plus 128",
        "host": "10.0.0.16",
        "port": 23,
        "location": "Rack 1",
        "notes": "12x8 (model numbers are IN x OUT). Only inputs 5-12 accept skew; "
                 "1-4 are VGA/analog pass-through. IP unconfirmed, powered off.",
        "enabled": True,
        "simulate": False,
    },
    {
        "device_id": "device.mtpx.sim",
        "type": "mtpx",
        "label": "MTPX Plus (simulated)",
        "host": "sim",
        "port": 23,
        "location": "Nowhere",
        "notes": "Simulation-mode MTPX. Exercises the skew/peaking/batch path without hardware.",
        "enabled": True,
        "simulate": True,
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
    # Some Extron boxes prompt on connect; the transport answers with these
    # (falling back to admin/admin, matching the lab's handshake).
    username: str = ""
    password: str = ""
    # Physical topology and telemetry support. This is an explicit configured
    # fallback until the adapter has a live, read-only discovery command for
    # the particular model/card family. It lets every client draw only real,
    # installed channels instead of assuming a largest-possible chassis.
    hardware_profile: dict[str, Any] = Field(default_factory=dict)
    # Optional ID in Joebot Lab's read-only telemetry API. If absent, Nexus
    # falls back to the known family mapping while the registry is migrated.
    lab_device_id: str = ""


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
        self.load_warnings: list[str] = self.load()

    def load(self) -> list[str]:
        """(Re)load the registry. A malformed or unknown-type entry never takes
        the service down — it's skipped and reported in the returned warnings,
        so hand-editing the .jbt stays a safe way to add devices."""
        path = self.settings.registry_path
        if not path.exists():
            doc = jbt.new("nexus_device_registry", {"devices": DEFAULT_DEVICES},
                          name="Joebot Studio Device Registry")
            jbt.save(path, doc)
        doc = jbt.load(path)
        warnings: list[str] = []
        self._entries.clear()
        for raw in doc["payload"].get("devices", []):
            try:
                config = DeviceConfig(**raw)
            except Exception as exc:
                warnings.append(f"skipped malformed device entry "
                                f"{raw.get('device_id', '?')!r}: {exc}")
                continue
            adapter_cls = ADAPTER_TYPES.get(config.type)
            if adapter_cls is None:
                warnings.append(f"skipped {config.device_id}: unknown type "
                                f"{config.type!r} (known: {', '.join(sorted(ADAPTER_TYPES))})")
                continue
            simulated = config.simulate or self.settings.simulate_all
            if simulated:
                transport = SimTransport(adapter_cls.Simulator())
            else:
                transport = TCPTransport(config.host, config.port,
                                         username=config.username,
                                         password=config.password)
            adapter = adapter_cls(config, transport)
            self._entries[config.device_id] = DeviceEntry(
                config=config, adapter=adapter, simulated=simulated)
        return warnings

    def get(self, device_id: str) -> DeviceEntry | None:
        return self._entries.get(device_id)

    def all(self) -> list[DeviceEntry]:
        return list(self._entries.values())
