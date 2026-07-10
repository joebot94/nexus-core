"""Shared Extron SIS family adapter.

Encodes the universal patterns from docs/reference/Extron_SIS_Reference.md:
preset recall is `{n}.` on every Extron device, queries are bare command
letters, and the E01–E28 error table is shared across the family. Model
subclasses override only what differs (e.g. MGP layout presets are `2*NN.`).

Protocol truth hierarchy: live-verified July 2026 code > deployed joebot-lab
code > March 2026 docs. Anything doc-only ships with verified=False.
"""

from __future__ import annotations

import re

from ..transports import TransportError
from .base import ActionResult, ActionSpec, DeviceAdapter

SIS_ERRORS = {
    "E01": "invalid input channel number",
    "E10": "invalid command",
    "E11": "invalid preset number",
    "E12": "invalid output number",
    "E13": "invalid value (out of range)",
    "E14": "invalid command for this configuration",
    "E17": "timeout (direct write of global presets)",
    "E21": "invalid room number",
    "E22": "busy",
    "E24": "privileges violation",
    "E25": "device not present",
    "E26": "maximum number of connections exceeded",
    "E27": "invalid event number",
    "E28": "bad filename / file not found",
}

_ERROR_RE = re.compile(r"^(E\d{2})\b")
# Connect banner: "(c) Copyright …, Extron Electronics, <model>, V<fw>, <part>"
_BANNER_MODEL_RE = re.compile(r"Extron Electronics[,.]?\s*([^,]+),\s*V?([\d.]+)", re.IGNORECASE)


class ExtronSISAdapter(DeviceAdapter):
    device_type = "extron_sis"

    actions = {
        "recall_preset": ActionSpec(
            summary="Recall preset N (universal Extron `N.`)",
            params={"preset": {"type": "int", "range": (1, 128), "required": True}},
        ),
        "query_firmware": ActionSpec(summary="Query firmware version (`Q`)"),
        "query_part_number": ActionSpec(summary="Query part number (`N`)"),
    }

    async def send(self, wire: str) -> ActionResult:
        """Send one SIS command, normalize transport failures and E-code errors."""
        try:
            reply = await self.transport.exchange(wire)
        except TransportError as exc:
            return ActionResult(ok=False, error=str(exc))
        match = _ERROR_RE.match(reply.response)
        if match:
            code = match.group(1)
            meaning = SIS_ERRORS.get(code, "unknown SIS error")
            return ActionResult(ok=False, response=reply.response,
                                error=f"{code}: {meaning}", latency_ms=reply.latency_ms)
        return ActionResult(ok=True, response=reply.response, latency_ms=reply.latency_ms)

    async def do_recall_preset(self, preset: int) -> ActionResult:
        result = await self.send(f"{preset}.")
        if result.ok and re.match(rf"Rpr\s*0*{preset}$", result.response):
            result.state = {"preset": preset}
        return result

    async def do_query_firmware(self) -> ActionResult:
        result = await self.send("Q")
        if result.ok:
            result.state = {"firmware": result.response}
            result.state_source = "query"
        return result

    async def do_query_part_number(self) -> ActionResult:
        result = await self.send("N")
        if result.ok:
            result.state = {"part_number": result.response}
            result.state_source = "query"
        return result

    async def probe(self) -> ActionResult:
        """Read-only identity check — the same safe `Q` GlitchBoard Phase 1 used."""
        try:
            reply = await self.transport.exchange("Q")
        except TransportError as exc:
            return ActionResult(ok=False, error=str(exc))
        state = {"firmware": reply.response}
        banner_match = _BANNER_MODEL_RE.search(reply.banner)
        if banner_match:
            state["model"] = banner_match.group(1).strip()
        result = ActionResult(ok=True, response=reply.response, latency_ms=reply.latency_ms)
        result.state = state
        return result
