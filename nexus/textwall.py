"""Opt-in relay to one configured TextWall renderer.

This is a deliberately narrow first slice of Nexus's coordination plane. It
does not treat TextWall as rack hardware and it never accepts a caller-provided
destination: the operator configures one endpoint with NEXUS_TEXTWALL_URL.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TextWallRelayResult:
    ok: bool
    status_code: int
    body: dict
    error: str | None = None


def _post(url: str, token: str, action: str, payload: dict) -> TextWallRelayResult:
    data = json.dumps({"action": action, "payload": payload}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-TextWall-Token"] = token
    request = Request(url + "/v1/textwall/commands", data=data,
                      headers=headers, method="POST")
    try:
        with urlopen(request, timeout=2.5) as response:  # noqa: S310 — URL is operator-configured
            raw = response.read()
            body = json.loads(raw.decode("utf-8")) if raw else {}
            return TextWallRelayResult(bool(body.get("ok")) and 200 <= response.status < 300,
                                        response.status, body)
    except HTTPError as exc:
        raw = exc.read()
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        return TextWallRelayResult(False, exc.code, body, body.get("message") or str(exc))
    except (URLError, OSError, TimeoutError) as exc:
        return TextWallRelayResult(False, 503, {}, str(exc.reason if isinstance(exc, URLError) else exc))


async def forward(url: str, token: str, action: str, payload: dict) -> TextWallRelayResult:
    return await asyncio.to_thread(_post, url.rstrip("/"), token, action, payload)
