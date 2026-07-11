"""Pydantic models for the /api/v1 contract."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ActionRequest(BaseModel):
    target: str = Field(description="device_id from the registry, e.g. 'device.mgp.1'")
    action: str = Field(description="normalized action name, e.g. 'recall_preset'")
    parameters: dict[str, Any] = Field(default_factory=dict)


class ActionResponse(BaseModel):
    ok: bool
    target: str
    action: str
    parameters: dict[str, Any]
    response: str = ""
    error: str | None = None
    latency_ms: int = 0
    state: dict[str, Any] = Field(default_factory=dict,
                                  description="state changes confirmed by the device ack")


class RawRequest(BaseModel):
    command: str = Field(description="raw SIS command, no terminator")
    confirm_raw: bool = Field(default=False,
                              description="must be true — raw access is diagnostics only")


class GroupActionRequest(BaseModel):
    action: str = Field(description="normalized action to fan out to every group member")
    parameters: dict[str, Any] = Field(default_factory=dict)


class VideowallPlanRequest(BaseModel):
    """A video-wall configuration to resolve into per-tile signal paths. The
    client (GlitchBoard) owns the config; Nexus resolves it statelessly."""
    tiles: int
    orientation: str = "horizontal"           # horizontal (rows) | vertical (cols)
    signal: str = "digital"                    # digital | rgb | composite
    builder_devices: list[str] = Field(default_factory=list)
    combiner_device: str = ""
    source_device: str = ""
    mtpx_devices: list[str] = Field(default_factory=list)
    dms_device: str = "device.dms.main"
    matrix_device: str = "device.matrix.main"
    smx_device: str = "device.smx.main"


class DeviceOut(BaseModel):
    device_id: str
    type: str
    label: str
    host: str
    port: int
    location: str
    notes: str
    enabled: bool
    simulated: bool
    status: str
    last_seen: str | None
    # How this device is connected (oneshot / pooled / lanes) and live transport
    # counters — for watching pooling/lanes behave during a rack session.
    connection: str = "oneshot"
    transport_stats: dict[str, Any] = Field(default_factory=dict)
