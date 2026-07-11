"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import VERSION
from .api.routes import router
from .api.ws import ws_router
from .config import Settings
from .events import EventBus
from .lab import LabTelemetryClient
from .lab import DEFAULT_LAB_IDS, LabTelemetryError
from .read_cache import ReadCache
from .registry import Registry
from .state import StateStore

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@dataclass
class Context:
    settings: Settings
    registry: Registry
    state: StateStore
    events: EventBus
    lab: LabTelemetryClient
    read_cache: ReadCache


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    ctx = Context(
        settings=settings,
        registry=Registry(settings),
        state=StateStore(),
        events=EventBus(settings.event_log_path),
        lab=LabTelemetryClient(settings.lab_url),
        read_cache=ReadCache(),
    )

    async def warm_read_cache() -> None:
        """Keep current DMS snapshots hot; never route or save anything."""
        next_names = 0.0
        while True:
            now = time.monotonic()
            for entry in ctx.registry.all():
                device_id = entry.config.device_id
                lab_id = entry.config.lab_device_id or DEFAULT_LAB_IDS.get(entry.config.type, "")
                if lab_id and ctx.settings.lab_url:
                    try:
                        ctx.read_cache.put_telemetry(device_id, await ctx.lab.device(lab_id))
                    except LabTelemetryError:
                        pass
                # DMS is the current interactive matrix. Polling all 36 ties
                # every ten seconds is bounded and keeps its patch bay instant.
                if entry.config.type == "dms3600":
                    ties: dict[int, int] = {}
                    for output in range(1, int(entry.adapter.hardware_profile().get("outputs", 36)) + 1):
                        result = await entry.adapter.execute("query_tie", {"output": output})
                        if result.ok and isinstance(result.state.get(f"output_{output}"), int):
                            ties[output] = result.state[f"output_{output}"]
                    if ties:
                        ctx.read_cache.put_routes(device_id, ties)
                    if now >= next_names:
                        for kind in ("input", "output", "preset"):
                            for start, count in ((1, 32), (33, 4)):
                                result = await entry.adapter.execute("read_name_bank", {"kind": kind, "start": start, "count": count})
                                names = result.state.get("names", {}).get(kind, {})
                                if result.ok and names:
                                    ctx.read_cache.put_names(device_id, kind, names)
            if now >= next_names:
                next_names = now + max(30, ctx.settings.name_cache_seconds)
            await asyncio.sleep(max(2, ctx.settings.cache_poll_seconds))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        devices = ctx.registry.all()
        ctx.events.emit("nexus", "nexus-core",
                        f"🦖 Nexus Core v{VERSION} up — {len(devices)} device(s) loaded, "
                        f"{sum(1 for d in devices if d.simulated)} simulated")
        for warning in ctx.registry.load_warnings:
            ctx.events.emit("nexus", "nexus-core", f"registry warning: {warning}")
        warm_task = asyncio.create_task(warm_read_cache())
        yield
        warm_task.cancel()
        with suppress(asyncio.CancelledError):
            await warm_task
        ctx.events.emit("nexus", "nexus-core", "Nexus Core shutting down")
        ctx.events.flush()

    app = FastAPI(
        title="Nexus Core",
        version=VERSION,
        description="Central hardware abstraction service for the Joebot AV lab. "
                    "Apps speak Nexus. Nexus speaks hardware. 🦖",
        lifespan=lifespan,
    )
    app.state.ctx = ctx
    app.include_router(router)
    app.include_router(ws_router)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/web", StaticFiles(directory=WEB_DIR), name="web")
    return app
