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
