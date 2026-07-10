"""REST routes for /api/v1."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import VERSION
from ..adapters.base import InvalidParams, UnsupportedAction
from ..registry import DeviceEntry
from .models import ActionRequest, ActionResponse, DeviceOut, RawRequest

router = APIRouter(prefix="/api/v1")
_started = time.monotonic()


def _ctx(request: Request):
    return request.app.state.ctx


def require_token(request: Request) -> None:
    token = _ctx(request).settings.token
    if not token:
        return
    supplied = request.headers.get("x-nexus-token", "")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        supplied = supplied or auth[7:]
    if supplied != token:
        raise HTTPException(401, "missing or invalid token")


def _device_out(entry: DeviceEntry) -> DeviceOut:
    cfg = entry.config
    return DeviceOut(
        device_id=cfg.device_id, type=cfg.type, label=cfg.label,
        host=cfg.host, port=cfg.port, location=cfg.location, notes=cfg.notes,
        enabled=cfg.enabled, simulated=entry.simulated,
        status=entry.status, last_seen=entry.last_seen,
    )


def _get_entry(request: Request, device_id: str) -> DeviceEntry:
    entry = _ctx(request).registry.get(device_id)
    if entry is None:
        raise HTTPException(404, f"unknown device: {device_id}")
    return entry


@router.get("/health")
def health(request: Request):
    ctx = _ctx(request)
    devices = ctx.registry.all()
    return {
        "ok": True,
        "service": "nexus-core",
        "version": VERSION,
        "uptime_s": int(time.monotonic() - _started),
        "devices": {
            "total": len(devices),
            "online": sum(1 for d in devices if d.status == "online"),
        },
    }


@router.get("/devices", response_model=list[DeviceOut], dependencies=[Depends(require_token)])
def list_devices(request: Request):
    return [_device_out(e) for e in _ctx(request).registry.all()]


@router.get("/devices/{device_id}", response_model=DeviceOut, dependencies=[Depends(require_token)])
def get_device(request: Request, device_id: str):
    return _device_out(_get_entry(request, device_id))


@router.get("/devices/{device_id}/state", dependencies=[Depends(require_token)])
def get_device_state(request: Request, device_id: str):
    entry = _get_entry(request, device_id)
    return {
        "device_id": device_id,
        "status": entry.status,
        "last_seen": entry.last_seen,
        "state": _ctx(request).state.snapshot(device_id),
    }


@router.get("/devices/{device_id}/capabilities", dependencies=[Depends(require_token)])
def get_capabilities(request: Request, device_id: str):
    return _get_entry(request, device_id).adapter.capabilities()


@router.post("/devices/{device_id}/probe", dependencies=[Depends(require_token)])
async def probe_device(request: Request, device_id: str):
    ctx = _ctx(request)
    entry = _get_entry(request, device_id)
    result = await entry.adapter.probe()
    entry.mark(result.ok)
    if result.ok:
        ctx.state.update(device_id, result.state, source="probe")
    label = entry.config.label or device_id
    summary = (f"{label} online — {result.state.get('model', 'fw ' + result.response)}"
               if result.ok else f"{label} unreachable: {result.error}")
    ctx.events.emit("device_status", device_id, summary,
                    {"ok": result.ok, "latency_ms": result.latency_ms, "state": result.state})
    return {"ok": result.ok, "status": entry.status, "latency_ms": result.latency_ms,
            "state": result.state, "error": result.error}


@router.get("/groups", dependencies=[Depends(require_token)])
def list_groups():
    # Logical groups/aliases land in M2 — the endpoint shape is stable now.
    return []


@router.post("/actions", response_model=ActionResponse, dependencies=[Depends(require_token)])
async def dispatch_action(request: Request, body: ActionRequest):
    ctx = _ctx(request)
    entry = _get_entry(request, body.target)
    if not entry.config.enabled:
        raise HTTPException(409, f"device {body.target} is disabled")
    try:
        result = await entry.adapter.execute(body.action, body.parameters)
    except UnsupportedAction as exc:
        raise HTTPException(400, str(exc)) from exc
    except InvalidParams as exc:
        raise HTTPException(422, str(exc)) from exc

    # An E-code error still proves the device answered — only a silent/failed
    # transport marks it offline.
    entry.mark(result.ok or bool(result.response))
    if result.ok and result.state:
        ctx.state.update(body.target, result.state, source=result.state_source)

    label = entry.config.label or body.target
    params = " ".join(f"{k}={v}" for k, v in body.parameters.items())
    summary = (f"{label}: {body.action} {params} ✓".strip()
               if result.ok else f"{label}: {body.action} {params} FAILED — {result.error}")
    response = ActionResponse(
        ok=result.ok, target=body.target, action=body.action,
        parameters=body.parameters, response=result.response,
        error=result.error, latency_ms=result.latency_ms, state=result.state,
    )
    ctx.events.emit("action_result", body.target, summary, response.model_dump())
    return response


@router.post("/devices/{device_id}/raw", dependencies=[Depends(require_token)])
async def raw_command(request: Request, device_id: str, body: RawRequest):
    """Guarded diagnostics access — NOT the integration path. Every use is logged."""
    ctx = _ctx(request)
    entry = _get_entry(request, device_id)
    if not body.confirm_raw:
        raise HTTPException(400, "raw access requires confirm_raw: true — "
                                 "use POST /api/v1/actions for normal control")
    if not hasattr(entry.adapter, "send"):
        raise HTTPException(400, f"{entry.config.type} does not support raw commands")
    result = await entry.adapter.send(body.command)
    ctx.events.emit("raw_command", device_id,
                    f"RAW to {entry.config.label or device_id}: {body.command!r} → "
                    f"{(result.response or result.error or '')!r}",
                    {"command": body.command, "ok": result.ok})
    return {"ok": result.ok, "response": result.response,
            "error": result.error, "latency_ms": result.latency_ms}


@router.get("/events", dependencies=[Depends(require_token)])
def list_events(request: Request, limit: int = 100):
    return _ctx(request).events.recent(min(max(limit, 1), 1000))
