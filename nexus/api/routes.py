"""REST routes for /api/v1."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import VERSION
from ..adapters.base import InvalidParams, UnsupportedAction
from ..lab import DEFAULT_LAB_IDS, LabTelemetryError
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


@router.get("/devices/{device_id}/hardware-profile", dependencies=[Depends(require_token)])
def get_hardware_profile(request: Request, device_id: str):
    """Read the best-known physical topology without sending any command.

    `source=configured` is intentionally explicit: it is a safe fallback until
    a model-specific, read-only discovery command has been live-verified.
    Clients use this to size their UI and validate old show files.
    """
    entry = _get_entry(request, device_id)
    return {
        "device_id": device_id,
        "status": entry.status,
        "last_seen": entry.last_seen,
        "profile": entry.adapter.hardware_profile(),
    }


@router.get("/devices/{device_id}/names", dependencies=[Depends(require_token)])
async def read_device_name_bank(request: Request, device_id: str, kind: str = "input",
                                start: int = 1, count: int = 32):
    """Read a small, explicit hardware-name bank through a dedicated adapter.

    Never use this endpoint as an accidental 128×128 sweep: adapters cap each
    request at 32 entries and reject a bank outside the installed profile.
    """
    entry = _get_entry(request, device_id)
    cached = _ctx(request).read_cache.names.get((device_id, kind))
    if cached is not None:
        stop = start + count - 1
        names = {key: value for key, value in cached.value.items() if start <= int(key) <= stop}
        if names:
            return {"ok": True, "kind": kind, "start": start, "count": count,
                    "names": names, "latency_ms": 0, "verified": False,
                    "cached": True, "cache_age_s": _ctx(request).read_cache.age_seconds(cached)}
    try:
        result = await entry.adapter.execute("read_name_bank", {
            "kind": kind, "start": start, "count": count})
    except UnsupportedAction as exc:
        raise HTTPException(400, str(exc)) from exc
    except InvalidParams as exc:
        raise HTTPException(422, str(exc)) from exc
    entry.mark(result.ok or bool(result.response))
    if not result.ok:
        return {"ok": False, "kind": kind, "start": start, "count": count,
                "names": {}, "error": result.error, "latency_ms": result.latency_ms}
    names = result.state.get("names", {}).get(kind, {})
    if names:
        _ctx(request).read_cache.put_names(device_id, kind, names)
    return {"ok": True, "kind": kind, "start": start, "count": count,
            "names": names, "latency_ms": result.latency_ms,
            "verified": entry.adapter.actions["read_name_bank"].verified}


@router.get("/devices/{device_id}/telemetry", dependencies=[Depends(require_token)])
async def get_lab_telemetry(request: Request, device_id: str):
    """Read Joebot Lab's existing poll result for one Nexus device.

    This is intentionally a read-only relay, not a second device poller. It is
    available only when an operator explicitly configures `NEXUS_LAB_URL`.
    Standalone Nexus command/probe operation never depends on Lab; a future
    Nexus-native telemetry scheduler will use the same normalized response
    shape when Lab is absent.
    """
    entry = _get_entry(request, device_id)
    lab_id = entry.config.lab_device_id or DEFAULT_LAB_IDS.get(entry.config.type, "")
    if not lab_id:
        raise HTTPException(404, f"no Joebot Lab mapping for {device_id}")
    cached = _ctx(request).read_cache.telemetry.get(device_id)
    if cached is not None:
        return {"device_id": device_id, "lab_device_id": lab_id, "telemetry": cached.value,
                "cached": True, "cache_age_s": _ctx(request).read_cache.age_seconds(cached)}
    try:
        telemetry = await _ctx(request).lab.device(lab_id)
    except LabTelemetryError as exc:
        raise HTTPException(503, str(exc)) from exc
    _ctx(request).read_cache.put_telemetry(device_id, telemetry)
    return {"device_id": device_id, "lab_device_id": lab_id, "telemetry": telemetry, "cached": False}


@router.get("/devices/{device_id}/routes", dependencies=[Depends(require_token)])
async def read_route_bank(request: Request, device_id: str, start: int = 1, count: int = 32,
                          plane: str | None = None):
    """Read a bounded bank of current output ties without changing a route.

    This is deliberately serial: matrix switchers are often one-command-at-a-
    time, and a full 128-output sweep would be rude. Clients request only the
    visible bank (DMS can safely request all 36 in two or fewer calls). The
    adapter's model-specific `query_tie` parser remains the source of truth.
    """
    entry = _get_entry(request, device_id)
    profile = entry.adapter.hardware_profile()
    outputs = int(profile.get("outputs") or 0)
    if outputs < 1:
        raise HTTPException(400, f"{device_id} does not report matrix outputs")
    if not 1 <= start <= outputs:
        raise HTTPException(422, f"start must be in range 1-{outputs}")
    if not 1 <= count <= 32:
        raise HTTPException(422, "count must be in range 1-32")
    stop = min(outputs, start + count - 1)
    cached = _ctx(request).read_cache.routes.get(device_id)
    if cached is not None:
        wanted = {str(output): cached.value[output] for output in range(start, stop + 1)
                  if output in cached.value}
        if len(wanted) == stop - start + 1:
            return {"ok": True, "device_id": device_id, "start": start,
                    "count": stop - start + 1, "plane": plane, "ties": wanted,
                    "errors": {}, "verified": True, "cached": True,
                    "cache_age_s": _ctx(request).read_cache.age_seconds(cached)}
    ties: dict[str, int] = {}
    errors: dict[str, str] = {}
    for output in range(start, stop + 1):
        params: dict[str, object] = {"output": output}
        if plane is not None:
            params["plane"] = plane
        try:
            result = await entry.adapter.execute("query_tie", params)
        except UnsupportedAction as exc:
            raise HTTPException(400, str(exc)) from exc
        except InvalidParams as exc:
            raise HTTPException(422, str(exc)) from exc
        entry.mark(result.ok or bool(result.response))
        input_value = result.state.get(f"output_{output}")
        if result.ok and isinstance(input_value, int):
            ties[str(output)] = input_value
        elif not result.ok:
            errors[str(output)] = result.error or "query failed"
    if ties:
        cached_ties = dict(cached.value) if cached is not None else {}
        cached_ties.update({int(key): value for key, value in ties.items()})
        _ctx(request).read_cache.put_routes(device_id, cached_ties)
    return {
        "ok": not errors,
        "device_id": device_id,
        "start": start,
        "count": stop - start + 1,
        "plane": plane,
        "ties": ties,
        "errors": errors,
        "verified": entry.adapter.actions["query_tie"].verified,
        "cached": False,
    }


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


@router.post("/registry/reload", dependencies=[Depends(require_token)])
def reload_registry(request: Request):
    """Re-read device_registry.jbt without restarting — edit the file, hit this,
    and the new device is live. State for existing devices is retained."""
    ctx = _ctx(request)
    warnings = ctx.registry.load()
    devices = ctx.registry.all()
    ctx.events.emit("nexus", "nexus-core",
                    f"registry reloaded — {len(devices)} device(s)"
                    + (f", {len(warnings)} skipped" if warnings else ""),
                    {"warnings": warnings})
    return {"ok": True, "devices": len(devices), "warnings": warnings}


@router.get("/events", dependencies=[Depends(require_token)])
def list_events(request: Request, limit: int = 100):
    return _ctx(request).events.recent(min(max(limit, 1), 1000))
