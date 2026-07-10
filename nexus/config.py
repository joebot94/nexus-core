"""Runtime settings — environment variables first, dev-friendly defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    host: str = field(default_factory=lambda: os.environ.get("NEXUS_HOST", "0.0.0.0"))
    # 8675 — Jenny. Not 8765. See docs/reference/Nexus_Architecture.md rule 5.
    port: int = field(default_factory=lambda: int(os.environ.get("NEXUS_PORT", "8675")))
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("NEXUS_DATA_DIR", "data")).expanduser())
    # Optional bearer token for LAN auth. Empty = auth disabled (trusted LAN).
    token: str = field(default_factory=lambda: os.environ.get("NEXUS_TOKEN", ""))
    # Force every device into simulation regardless of registry flags.
    simulate_all: bool = field(default_factory=lambda: os.environ.get("NEXUS_SIMULATE", "") == "1")

    @property
    def registry_path(self) -> Path:
        override = os.environ.get("NEXUS_REGISTRY", "")
        return Path(override).expanduser() if override else self.data_dir / "jbt" / "device_registry.jbt"

    @property
    def event_log_path(self) -> Path:
        return self.data_dir / "logs" / "nexus_rolling.jbt"
