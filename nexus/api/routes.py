"""REST routes for /api/v1."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import VERSION
from ..adapters.base import InvalidParams, UnsupportedAction
from ..lab import DEFAULT_LAB_IDS, LabTelemetryError
from ..registry import DeviceEntry
from ..transports import LanePoolTransport, PooledTransport
from .models import (ActionRequest, ActionResponse, DeviceOut,
                     GroupActionRequest, RawRequest, VideowallPlanRequest,
                     VideowallChaosRequest, VideowallFreezeRequest,
                     VideowallScrambleRequest, VideowallSkewRequest)

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
    transport = entry.adapter.transport
    stats = dict(getattr(transport, "stats", {}) or {})
    if isinstance(transport, LanePoolTransport):
        stats["lane_count"] = transport.lane_count
        stats["lanes_live"] = sum(1 for l in transport._lanes if l.alive)
    return DeviceOut(
        device_id=cfg.device_id, type=cfg.type, label=cfg.label,
        host=cfg.host, port=cfg.port, location=cfg.location, notes=cfg.notes,
        enabled=cfg.enabled, simulated=entry.simulated,
        status=entry.status, last_seen=entry.last_seen,
        connection=cfg.connection, transport_stats=stats,
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
    # Plane-aware devices (SMX) get their own cache slot per plane so VGA and
    # Audio banks can't shadow each other.
    cache_key = device_id if plane is None else f"{device_id}#{plane}"
    cached = _ctx(request).read_cache.routes.get(cache_key)
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
        # Flat matrices report `output_N`; plane-aware adapters (SMX) report
        # `plane_PP_output_N` (even for their default plane). Accept either so
        # no device family returns a silently empty bank.
        input_value = result.state.get(f"output_{output}")
        if input_value is None:
            input_value = next((v for k, v in result.state.items()
                                if k.endswith(f"output_{output}") and isinstance(v, int)), None)
        if result.ok and isinstance(input_value, int):
            ties[str(output)] = input_value
        elif not result.ok:
            errors[str(output)] = result.error or "query failed"
    if ties:
        cached_ties = dict(cached.value) if cached is not None else {}
        cached_ties.update({int(key): value for key, value in ties.items()})
        _ctx(request).read_cache.put_routes(cache_key, cached_ties)
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


async def _run_action(ctx, entry: DeviceEntry, action: str,
                      parameters: dict) -> ActionResponse:
    """Execute one normalized action on one device, updating state + events.
    Shared by /actions, group fan-out, and scene recall so all three stay
    identical in how they mark status, record state, and log. Raises the same
    HTTPExceptions dispatch_action historically did."""
    if not entry.config.enabled:
        raise HTTPException(409, f"device {entry.config.device_id} is disabled")
    try:
        result = await entry.adapter.execute(action, parameters)
    except UnsupportedAction as exc:
        raise HTTPException(400, str(exc)) from exc
    except InvalidParams as exc:
        raise HTTPException(422, str(exc)) from exc

    # An E-code error still proves the device answered — only a silent/failed
    # transport marks it offline.
    entry.mark(result.ok or bool(result.response))
    if result.ok and result.state:
        ctx.state.update(entry.config.device_id, result.state, source=result.state_source)

    label = entry.config.label or entry.config.device_id
    params = " ".join(f"{k}={v}" for k, v in parameters.items())
    summary = (f"{label}: {action} {params} ✓".strip()
               if result.ok else f"{label}: {action} {params} FAILED — {result.error}")
    response = ActionResponse(
        ok=result.ok, target=entry.config.device_id, action=action,
        parameters=parameters, response=result.response,
        error=result.error, latency_ms=result.latency_ms, state=result.state,
    )
    ctx.events.emit("action_result", entry.config.device_id, summary, response.model_dump())
    return response


async def _run_step(ctx, device_id: str, action: str, parameters: dict) -> dict:
    """Per-step execution for scenes/groups. NEVER raises — an unknown device or
    an unsupported/invalid action is recorded as a failed step so one bad step
    doesn't abort the whole batch (e.g. a not-yet-wired IR source-mode step)."""
    entry = ctx.registry.get(device_id)
    if entry is None:
        return {"target": device_id, "action": action, "ok": False,
                "error": "unknown device (not in registry)"}
    try:
        return (await _run_action(ctx, entry, action, parameters)).model_dump()
    except HTTPException as exc:
        return {"target": device_id, "action": action, "ok": False,
                "error": f"{exc.status_code}: {exc.detail}"}


@router.get("/groups", dependencies=[Depends(require_token)])
def list_groups(request: Request):
    """Named aliases for sets of device targets. Post one action to a group and
    it fans out to every member (`POST /groups/{id}/actions`)."""
    return [g.model_dump() for g in _ctx(request).scenes.groups.values()]


@router.post("/groups/{group_id}/actions", dependencies=[Depends(require_token)])
async def group_action(request: Request, group_id: str, body: GroupActionRequest):
    """Fan one action out to every member of a group, in registry order.
    Continues past a failing member and reports each; overall ok = all ok."""
    ctx = _ctx(request)
    targets = ctx.scenes.resolve_group(group_id)
    if targets is None:
        raise HTTPException(404, f"unknown group: {group_id}")
    results = [await _run_step(ctx, device_id, body.action, body.parameters)
               for device_id in targets]
    ok = bool(results) and all(r.get("ok") for r in results)
    ctx.events.emit("group_action", group_id,
                    f"group {group_id}: {body.action} → {len(results)} member(s) "
                    + ("✓" if ok else "with failures"))
    return {"ok": ok, "group": group_id, "action": body.action,
            "parameters": body.parameters, "results": results}


@router.get("/wall/plan", dependencies=[Depends(require_token)])
def wall_plan(request: Request):
    """Resolve the MTPX video wall from registry placement metadata into a
    planning artifact: per-slot lanes, the physical loopback patch list, baseline
    tie sets, the Matrix 12800 identity routing, and MGP assignment. Read-only
    and fires nothing — planning truth for a graphical wall view and for racking
    the loopback cables. See docs/MTPX-WALL-DESIGN.md."""
    from ..wallplan import WallPlanError, plan_from_registry

    ctx = _ctx(request)
    units = [
        {"name": e.config.device_id, "wall_model": e.config.wall_model,
         "host": e.config.host, "wall_slots": e.config.wall_slots,
         "wall_passes": e.config.wall_passes}
        for e in ctx.registry.all() if e.config.type == "mtpx"
    ]
    slotted = [u for u in units if u["wall_slots"]]
    if not slotted:
        return {"configured": False, "units": len(units),
                "note": "no MTPX devices carry wall_slots yet — add placement "
                        "in the registry (docs/MTPX-WALL-DESIGN.md)"}
    try:
        plan = plan_from_registry(units)
    except WallPlanError as exc:
        raise HTTPException(422, f"wall plan invalid: {exc}") from exc
    return {
        "configured": True,
        "lanes": [
            {"slot": l.slot, "unit": l.unit, "inputs": l.inputs,
             "outputs": l.outputs, "matrix_input": l.matrix_input,
             "passes": l.passes, "max_skew": l.max_skew}
            for l in plan.lanes
        ],
        "patch_list": plan.patch_list(),
        "unit_ties": plan.unit_ties(),
        "matrix_ties": plan.matrix_ties(),
        "mgp_assignment": plan.mgp_assignment(),
        "warnings": plan.warnings,
    }


@router.post("/wall/baseline-scene", dependencies=[Depends(require_token)])
def generate_wall_baseline(request: Request):
    """Generate the 'normal' baseline scene from the current wall plan (per-lane
    MTPX ties + skew-0, Matrix identity routing, MGP clean layout) and save it
    as `scene.wall-baseline`. Fires nothing — recall/dry-run it via /scenes.
    MTPX steps are verified=false, so live recall stays bench-gated."""
    from ..scenes import build_wall_baseline_scene
    from ..wallplan import WallPlanError, plan_from_registry

    ctx = _ctx(request)
    units = [
        {"name": e.config.device_id, "wall_model": e.config.wall_model,
         "host": e.config.host, "wall_slots": e.config.wall_slots,
         "wall_passes": e.config.wall_passes}
        for e in ctx.registry.all()
        if e.config.type == "mtpx" and e.config.wall_slots
    ]
    if not units:
        raise HTTPException(422, "no MTPX devices carry wall_slots — configure "
                                 "placement first (GET /wall/plan)")
    try:
        plan = plan_from_registry(units)
    except WallPlanError as exc:
        raise HTTPException(422, f"wall plan invalid: {exc}") from exc
    scene = build_wall_baseline_scene(plan)
    ctx.scenes.upsert_scene(scene)
    ctx.events.emit("nexus", "nexus-core",
                    f"generated {scene.id} — {len(scene.steps)} steps from wall plan")
    return {"ok": True, "scene": scene.model_dump(),
            "hint": "dry-run with POST /scenes/scene.wall-baseline/recall?dry_run=true"}


@router.post("/wall/videowall/plan", dependencies=[Depends(require_token)])
def videowall_plan(request: Request, body: VideowallPlanRequest):
    """Resolve a video-wall config into every tile's full signal path through the
    DMS fabric (source → builder MGP → combiner MGP → out, per signal style) plus
    each tile's builder/window. Read-only planning truth for GlitchBoard's wall
    view — the map that lets skew/scramble target the right square. Fires nothing.
    See GlitchBoard/docs/VIDEOWALL-MGP-DESIGN.md."""
    from ..videowall import (Orientation, Signal, VideowallError, WallConfig,
                             builder_window, cells, tile_path)
    try:
        wall = WallConfig(
            tiles=body.tiles, orientation=Orientation(body.orientation),
            signal=Signal(body.signal), builder_devices=body.builder_devices,
            combiner_device=body.combiner_device, source_device=body.source_device,
            mtpx_devices=body.mtpx_devices, dms_device=body.dms_device,
            matrix_device=body.matrix_device, smx_device=body.smx_device)
        spec = wall.layout
    except VideowallError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, f"invalid orientation/signal: {exc}") from exc

    resolved = []
    for tile in cells(spec):
        builder_i, window = builder_window(tile, wall)
        resolved.append({
            "row": tile.row, "col": tile.col,
            "builder_index": builder_i, "window": window,
            "path": [{"stage": h.stage, "device": h.device, "detail": h.detail}
                     for h in tile_path(tile, wall)],
        })
    return {"tiles": body.tiles, "grid": f"{spec.rows}×{spec.cols}",
            "signal": body.signal, "single_mgp": wall.is_single_mgp,
            "builder_preset": spec.builder_preset,
            "combiner_preset": spec.combiner_preset, "resolved": resolved}


@router.post("/wall/videowall/baseline-scene", dependencies=[Depends(require_token)])
def videowall_baseline_scene(request: Request, body: VideowallPlanRequest):
    """Generate the video wall's 'normal' baseline (source grid-mode, builder/
    combiner MGP presets, identity DMS routing) from a wall config and save it as
    `scene.videowall-baseline`. Fires nothing — recall/dry-run via /scenes. The
    source-mode step is IR-via-IPCP (pending the EIR scan), so it's dry-runnable
    but not yet live-fireable; scene recall records it as a failed step and keeps
    going rather than aborting."""
    from ..scenes import Scene, SceneStep
    from ..videowall import (Orientation, Signal, VideowallError, WallConfig,
                             baseline_steps)
    ctx = _ctx(request)
    try:
        wall = WallConfig(
            tiles=body.tiles, orientation=Orientation(body.orientation),
            signal=Signal(body.signal), builder_devices=body.builder_devices,
            combiner_device=body.combiner_device, source_device=body.source_device,
            mtpx_devices=body.mtpx_devices, dms_device=body.dms_device,
            matrix_device=body.matrix_device, smx_device=body.smx_device)
        steps = baseline_steps(wall)
    except VideowallError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, f"invalid orientation/signal: {exc}") from exc

    scene = Scene(id="scene.videowall-baseline",
                  label=f"Videowall baseline ({wall.layout.rows}×{wall.layout.cols} {body.signal})",
                  notes="Generated from a wall config. Source grid-mode is IR via "
                        "the IPCP (pending EIR scan); the rest is MGP presets + DMS "
                        "identity routing. Dry-run freely; scrambles layer on top.",
                  steps=[SceneStep(**s) for s in steps])
    ctx.scenes.upsert_scene(scene)
    ctx.events.emit("nexus", "nexus-core",
                    f"generated {scene.id} — {len(scene.steps)} steps from videowall config")
    return {"ok": True, "scene": scene.model_dump(),
            "hint": "dry-run: POST /scenes/scene.videowall-baseline/recall?dry_run=true"}


@router.post("/wall/videowall/scramble-scene", dependencies=[Depends(require_token)])
def videowall_scramble_scene(request: Request, body: VideowallScrambleRequest):
    """Generate an input-remap scramble as a chaos DELTA on the baseline —
    permute which source feeds each window on the chosen builder MGPs (deranged,
    deterministic from `seed`). Saved as `scene.videowall-scramble`, dry-runnable.
    `builders: [0]` = scramble only that region; empty = the whole wall."""
    from ..scenes import Scene, SceneStep
    from ..videowall import (Orientation, Signal, VideowallError, WallConfig,
                             scramble_steps)
    ctx = _ctx(request)
    try:
        wall = WallConfig(
            tiles=body.tiles, orientation=Orientation(body.orientation),
            signal=Signal(body.signal), builder_devices=body.builder_devices,
            combiner_device=body.combiner_device, source_device=body.source_device,
            mtpx_devices=body.mtpx_devices, dms_device=body.dms_device,
            matrix_device=body.matrix_device, smx_device=body.smx_device)
        steps = scramble_steps(wall, builders=body.builders or None, seed=body.seed)
    except VideowallError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, f"invalid orientation/signal: {exc}") from exc

    if not steps:
        raise HTTPException(422, "nothing to scramble (a 1-wide layout has no "
                                 "windows to permute)")
    scene = Scene(id="scene.videowall-scramble",
                  label=f"Videowall scramble (seed {body.seed})",
                  notes="Input-remap chaos delta on the baseline. Fast (~15Hz), "
                        "no handshake; tiles keep position, sources shuffle.",
                  steps=[SceneStep(**s) for s in steps])
    ctx.scenes.upsert_scene(scene)
    ctx.events.emit("nexus", "nexus-core",
                    f"generated {scene.id} — {len(scene.steps)} route steps")
    return {"ok": True, "scene": scene.model_dump(),
            "hint": "dry-run: POST /scenes/scene.videowall-scramble/recall?dry_run=true"}


@router.post("/wall/videowall/skew-scene", dependencies=[Depends(require_token)])
def videowall_skew_scene(request: Request, body: VideowallSkewRequest):
    """Generate an MTPX skew burst as a chaos DELTA — RGB line-skew (0-31 =
    0-62ns) on the chosen tiles, targeting the right MTPX input via each tile's
    resolved path. RGB walls only. Saved as `scene.videowall-skew`, dry-runnable.
    `random: true` = deterministic per-tile skew from `seed`; else uniform r/g/b."""
    from ..scenes import Scene, SceneStep
    from ..videowall import (Orientation, Signal, VideowallError, WallConfig,
                             cells, skew_burst_steps)
    ctx = _ctx(request)
    try:
        wall = WallConfig(
            tiles=body.tiles,
            orientation=Orientation(body.orientation), signal=Signal(body.signal),
            builder_devices=body.builder_devices, combiner_device=body.combiner_device,
            source_device=body.source_device, mtpx_devices=body.mtpx_devices,
            dms_device=body.dms_device, matrix_device=body.matrix_device,
            smx_device=body.smx_device)
        all_tiles = cells(wall.layout)
    except (VideowallError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    # tile_indices resolve against the grid (empty = whole wall).
    chosen = [all_tiles[i] for i in body.tile_indices if 0 <= i < len(all_tiles)] or None
    steps = skew_burst_steps(
        wall, tiles=chosen, r=body.r, g=body.g, b=body.b,
        random_seed=body.seed if body.random else None, max_skew=body.max_skew)
    if not steps:
        raise HTTPException(422, "skew is RGB-path only — this wall's signal is "
                                 f"'{body.signal}' (skew ghosts on digital/composite)")
    scene = Scene(id="scene.videowall-skew",
                  label=f"Videowall skew ({'random ' if body.random else ''}burst)",
                  notes="MTPX RGB line-skew chaos delta on the baseline. RGB path "
                        "only; targets each tile's MTPX input via its resolved path.",
                  steps=[SceneStep(**s) for s in steps])
    ctx.scenes.upsert_scene(scene)
    ctx.events.emit("nexus", "nexus-core",
                    f"generated {scene.id} — {len(scene.steps)} MTPX skew step(s)")
    return {"ok": True, "scene": scene.model_dump(),
            "hint": "dry-run: POST /scenes/scene.videowall-skew/recall?dry_run=true"}


@router.post("/wall/videowall/freeze-scene", dependencies=[Depends(require_token)])
def videowall_freeze_scene(request: Request, body: VideowallFreezeRequest):
    """Freeze or blank chosen tiles (the FX-chase stutter) as a chaos DELTA.
    `mode`: freeze | blank. Saved as `scene.videowall-freeze`, dry-runnable."""
    from ..scenes import Scene, SceneStep
    from ..videowall import (Orientation, Signal, VideowallError, WallConfig,
                             cells, freeze_steps)
    ctx = _ctx(request)
    try:
        wall = WallConfig(
            tiles=body.tiles, orientation=Orientation(body.orientation),
            signal=Signal(body.signal), builder_devices=body.builder_devices,
            combiner_device=body.combiner_device, source_device=body.source_device,
            mtpx_devices=body.mtpx_devices, dms_device=body.dms_device,
            matrix_device=body.matrix_device, smx_device=body.smx_device)
        all_tiles = cells(wall.layout)
        chosen = [all_tiles[i] for i in body.tile_indices if 0 <= i < len(all_tiles)] or None
        steps = freeze_steps(wall, tiles=chosen, mode=body.mode, on=body.on)
    except (VideowallError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc

    scene = Scene(id="scene.videowall-freeze",
                  label=f"Videowall {body.mode} ({'on' if body.on else 'release'})",
                  notes="MGP window freeze/blank chaos delta on the baseline.",
                  steps=[SceneStep(**s) for s in steps])
    ctx.scenes.upsert_scene(scene)
    ctx.events.emit("nexus", "nexus-core",
                    f"generated {scene.id} — {len(scene.steps)} {body.mode} step(s)")
    return {"ok": True, "scene": scene.model_dump(),
            "hint": "dry-run: POST /scenes/scene.videowall-freeze/recall?dry_run=true"}


@router.post("/wall/videowall/chaos-scene", dependencies=[Depends(require_token)])
def videowall_chaos_scene(request: Request, body: VideowallChaosRequest):
    """Compose the glitch toolkit per region into ONE chaos delta — scramble +
    skew + freeze on the regions you name, everything else clean. This is the
    "one quadrant crazy, rest untouched" control. Saved as `scene.videowall-
    chaos`, dry-runnable. Deterministic from `seed`."""
    from ..scenes import Scene, SceneStep
    from ..videowall import (Orientation, RegionChaos, Signal, VideowallError,
                             WallConfig, chaos_steps)
    ctx = _ctx(request)
    try:
        wall = WallConfig(
            tiles=body.tiles, orientation=Orientation(body.orientation),
            signal=Signal(body.signal), builder_devices=body.builder_devices,
            combiner_device=body.combiner_device, source_device=body.source_device,
            mtpx_devices=body.mtpx_devices, dms_device=body.dms_device,
            matrix_device=body.matrix_device, smx_device=body.smx_device)
        wall.layout   # validate grid
    except (VideowallError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    regions = [RegionChaos(builder=r.builder, scramble=r.scramble, skew=r.skew,
                           freeze=r.freeze) for r in body.regions]
    steps = chaos_steps(wall, regions, seed=body.seed)
    if not steps:
        raise HTTPException(422, "no chaos requested — name at least one region "
                                 "with scramble/skew/freeze")
    scene = Scene(id="scene.videowall-chaos",
                  label=f"Videowall chaos ({len(regions)} region(s), seed {body.seed})",
                  notes="Composed glitch delta — scramble + skew + freeze per "
                        "region, unnamed regions clean. Layers on the baseline.",
                  steps=[SceneStep(**s) for s in steps])
    ctx.scenes.upsert_scene(scene)
    ctx.events.emit("nexus", "nexus-core",
                    f"generated {scene.id} — {len(scene.steps)} steps across "
                    f"{len(regions)} region(s)")
    return {"ok": True, "scene": scene.model_dump(),
            "hint": "dry-run: POST /scenes/scene.videowall-chaos/recall?dry_run=true"}


@router.get("/scenes", dependencies=[Depends(require_token)])
def list_scenes(request: Request):
    """Named, ordered cross-device recalls — the baseline + chaos deltas."""
    return [s.model_dump() for s in _ctx(request).scenes.scenes.values()]


@router.post("/scenes/{scene_id}/recall", dependencies=[Depends(require_token)])
async def recall_scene(request: Request, scene_id: str, dry_run: bool = False):
    """Run a scene's steps in order (expanding groups) through the same adapter
    path a single action uses. `dry_run=true` resolves + validates the steps
    and returns them without firing — the safe preview before a real recall.
    Continues past a failing step; overall ok = all steps ok."""
    ctx = _ctx(request)
    scene = ctx.scenes.scenes.get(scene_id)
    if scene is None:
        raise HTTPException(404, f"unknown scene: {scene_id}")
    steps = ctx.scenes.expand(scene)
    known = {e.config.device_id for e in ctx.registry.all()}

    if dry_run:
        return {"ok": True, "scene": scene_id, "dry_run": True,
                "steps": [{"target": s.target, "action": s.action,
                           "parameters": s.parameters,
                           "known_device": s.target in known} for s in steps]}

    results = [await _run_step(ctx, step.target, step.action, step.parameters)
               for step in steps]
    ok = bool(results) and all(r.get("ok") for r in results)
    ctx.events.emit("scene_recall", scene_id,
                    f"scene {scene_id} ({scene.label}): {len(results)} step(s) "
                    + ("✓" if ok else "with failures"))
    return {"ok": ok, "scene": scene_id, "label": scene.label, "results": results}


@router.post("/scenes/reload", dependencies=[Depends(require_token)])
def reload_scenes(request: Request):
    """Re-read scenes.jbt without restarting — hand-edit + reload, like the
    device registry."""
    ctx = _ctx(request)
    warnings = ctx.scenes.load()
    ctx.events.emit("nexus", "nexus-core",
                    f"scenes reloaded — {len(ctx.scenes.groups)} group(s), "
                    f"{len(ctx.scenes.scenes)} scene(s)"
                    + (f", {len(warnings)} skipped" if warnings else ""),
                    {"warnings": warnings})
    return {"ok": True, "groups": len(ctx.scenes.groups),
            "scenes": len(ctx.scenes.scenes), "warnings": warnings}


@router.post("/actions", response_model=ActionResponse, dependencies=[Depends(require_token)])
async def dispatch_action(request: Request, body: ActionRequest):
    ctx = _ctx(request)
    entry = _get_entry(request, body.target)
    return await _run_action(ctx, entry, body.action, body.parameters)


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
async def reload_registry(request: Request):
    """Re-read device_registry.jbt without restarting — edit the file, hit this,
    and the new device is live. State for existing devices is retained."""
    ctx = _ctx(request)
    # Reload rebuilds every adapter: close the outgoing pooled sockets so no
    # reader task keeps an orphaned connection to the rack…
    old_pools = [entry.adapter.transport for entry in ctx.registry.all()
                 if isinstance(entry.adapter.transport, PooledTransport)]
    warnings = ctx.registry.load()
    for pool in old_pools:
        await pool.aclose()
    # …and re-attach unsolicited listeners on the fresh ones.
    if ctx.wire_pools:
        ctx.wire_pools()
    devices = ctx.registry.all()
    ctx.events.emit("nexus", "nexus-core",
                    f"registry reloaded — {len(devices)} device(s)"
                    + (f", {len(warnings)} skipped" if warnings else ""),
                    {"warnings": warnings})
    return {"ok": True, "devices": len(devices), "warnings": warnings}


@router.get("/events", dependencies=[Depends(require_token)])
def list_events(request: Request, limit: int = 100):
    return _ctx(request).events.recent(min(max(limit, 1), 1000))
