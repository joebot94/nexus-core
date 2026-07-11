"""FastAPI application factory."""

from __future__ import annotations

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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    ctx = Context(
        settings=settings,
        registry=Registry(settings),
        state=StateStore(),
        events=EventBus(settings.event_log_path),
        lab=LabTelemetryClient(settings.lab_url),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        devices = ctx.registry.all()
        ctx.events.emit("nexus", "nexus-core",
                        f"🦖 Nexus Core v{VERSION} up — {len(devices)} device(s) loaded, "
                        f"{sum(1 for d in devices if d.simulated)} simulated")
        for warning in ctx.registry.load_warnings:
            ctx.events.emit("nexus", "nexus-core", f"registry warning: {warning}")
        yield
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
