"""WebSocket event stream — /api/v1/ws.

Pushes every EventBus event (device_status, action_result, raw_command, log)
as JSON. Clients may send {"type": "ping"} and get {"type": "pong"}.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()


@ws_router.websocket("/api/v1/ws")
async def event_stream(websocket: WebSocket):
    ctx = websocket.app.state.ctx
    token = ctx.settings.token
    if token and websocket.query_params.get("token", "") != token:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    queue = ctx.events.subscribe()
    await websocket.send_json({"type": "hello", "service": "nexus-core",
                               "events_buffered": len(ctx.events.recent(1000))})

    async def pump_events():
        while True:
            event = await queue.get()
            await websocket.send_json({"type": "event", "event": event})

    async def pump_client():
        while True:
            text = await websocket.receive_text()
            with contextlib.suppress(json.JSONDecodeError):
                if json.loads(text).get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

    tasks = [asyncio.create_task(pump_events()), asyncio.create_task(pump_client())]
    try:
        done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            # Consume the disconnect exception so asyncio doesn't log
            # "exception was never retrieved" for a normal client close.
            with contextlib.suppress(Exception):
                task.exception()
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        ctx.events.unsubscribe(queue)
