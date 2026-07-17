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
_NAME_RESPONSE_RE = re.compile(r"^Nm[IOG]\d+(?:\*\d+)?,\s*(.+)$", re.IGNORECASE)
# Unsolicited broadcast shapes (mirror the ack forms; live-listening pass pending).
_UNSOL_PRESET_RE = re.compile(r"^Rpr\s*0*(\d{1,3})$")
_UNSOL_TIE_RE = re.compile(r"^Out\s*0*(\d{1,3})\s+In\s*0*(\d{1,3})")


def name_bank_action(kinds: list[str]) -> ActionSpec:
    return ActionSpec(
        summary="Read a bounded bank of hardware-stored channel/preset names. "
                "Read-only; use 32 or fewer entries per request.",
        params={
            "kind": {"enum": kinds, "required": True},
            "start": {"type": "int", "range": (1, 128), "required": False, "default": 1},
            "count": {"type": "int", "range": (1, 32), "required": False, "default": 32},
        },
        verified=False,
    )


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

    async def read_name_bank(self, kind: str, start: int, count: int,
                             limits: dict[str, int]) -> ActionResult:
        """Read `ESC n NI/NO/NG` names over one socket without a full sweep."""
        limit = limits.get(kind, 0)
        if not limit:
            from .base import InvalidParams
            raise InvalidParams(f"{self.device_type} does not expose {kind} names")
        if start > limit or start + count - 1 > limit:
            from .base import InvalidParams
            raise InvalidParams(f"{kind} name bank must fit in range 1-{limit}")
        suffix = {"input": "NI", "output": "NO", "preset": "NG"}[kind]
        wires = [f"\x1b{channel}{suffix}" for channel in range(start, start + count)]
        try:
            replies = await self.transport.exchange_sequence(wires)
        except TransportError as exc:
            return ActionResult(ok=False, error=str(exc))
        names: dict[str, str] = {}
        for channel, reply in zip(range(start, start + count), replies):
            if name := self._parse_name(reply.response):
                names[str(channel)] = name
        return ActionResult(ok=True, response=f"{len(names)}/{count} {kind} names",
                            latency_ms=sum(r.latency_ms for r in replies),
                            state={"names": {kind: names}}, state_source="query")

    @staticmethod
    def parse_tie_pairs(ties: list, max_input: int, max_output: int) -> list[tuple[int, int]]:
        """Validate a quick-multiple-tie list (`[{"input": i, "output": o}, ...]`)
        into (input, output) pairs. Input 0 unties. One output may only appear
        once — the whole point is ONE atomic switch, so a duplicate output is an
        authoring error, not a sequence. Capped at 32 pairs per command until the
        real per-device command-line length limit is bench-measured."""
        from .base import InvalidParams
        if len(ties) < 2:
            raise InvalidParams("tie_many needs at least 2 ties — use 'tie' for one")
        if len(ties) > 32:
            raise InvalidParams("tie_many is capped at 32 pairs per command")
        pairs: list[tuple[int, int]] = []
        seen_outputs: set[int] = set()
        for item in ties:
            if not isinstance(item, dict) or "input" not in item or "output" not in item:
                raise InvalidParams('each tie must be {"input": N, "output": N}')
            try:
                inp, out = int(item["input"]), int(item["output"])
            except (TypeError, ValueError):
                raise InvalidParams("tie input/output must be integers") from None
            if not 0 <= inp <= max_input:
                raise InvalidParams(f"tie input {inp} out of range 0-{max_input}")
            if not 1 <= out <= max_output:
                raise InvalidParams(f"tie output {out} out of range 1-{max_output}")
            if out in seen_outputs:
                raise InvalidParams(f"output {out} appears twice in one tie_many")
            seen_outputs.add(out)
            pairs.append((inp, out))
        return pairs

    @staticmethod
    def _parse_name(raw: str) -> str | None:
        cleaned = raw.strip().rstrip("]\r\n")
        if not cleaned or cleaned.startswith(("E", "Password:", "Login ", "(c) Copyright")):
            return None
        if match := _NAME_RESPONSE_RE.match(cleaned):
            return match.group(1).strip() or None
        if "," in cleaned:
            return cleaned.split(",", 1)[1].strip() or None
        return cleaned

    def parse_unsolicited(self, line: str) -> dict:
        """Family-wide broadcast shapes: a front-panel preset recall echoes the
        same `RprNN` an acked recall does; a tie change echoes `OutNN InNN`."""
        if match := _UNSOL_PRESET_RE.match(line):
            return {"preset": int(match.group(1))}
        if match := _UNSOL_TIE_RE.match(line):
            return {f"output_{int(match.group(1))}": int(match.group(2))}
        return {}

    async def probe(self) -> ActionResult:
        """Read-only identity check — the same safe `Q` GlitchBoard Phase 1 used.
        Any reply (even an E-code) proves the device is online; only silence or
        a transport failure counts as offline."""
        try:
            reply = await self.transport.exchange("Q")
        except TransportError as exc:
            return ActionResult(ok=False, error=str(exc))
        state = {}
        if not _ERROR_RE.match(reply.response):
            state["firmware"] = reply.response
        banner_match = _BANNER_MODEL_RE.search(reply.banner)
        if banner_match:
            state["model"] = banner_match.group(1).strip()
        result = ActionResult(ok=True, response=reply.response, latency_ms=reply.latency_ms)
        result.state = state
        return result

    class Simulator(DeviceAdapter.Simulator):
        """Generic Extron SIS box: universal preset recall + identity queries.
        Lets ANY Extron device join the registry as type `extron_sis` before it
        has a dedicated adapter."""
        banner = "(c) Copyright 2024, Extron Electronics, SIS Device, V1.00, 60-0000-01"

        def __init__(self) -> None:
            self.preset = 0
            self.names: dict[tuple[str, int], str] = {}

        def respond(self, command: str) -> str:
            if command == "Q":
                return "1.00"
            if command == "N":
                return "60-0000-01"
            if match := re.fullmatch(r"(\d{1,3})\.", command):
                self.preset = int(match.group(1))
                return f"Rpr{self.preset:02d}"
            if match := re.fullmatch(r"\x1b(\d+)(NI|NO|NG)", command):
                channel, suffix = int(match.group(1)), match.group(2)
                kind = {"NI": "I", "NO": "O", "NG": "G"}[suffix]
                default = {"I": f"Input {channel}", "O": f"Output {channel}", "G": f"Preset {channel}"}[kind]
                return f"Nm{kind}{channel},{self.names.get((kind, channel), default)}"
            return "E10"
