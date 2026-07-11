"""Extron MTPX Plus adapter — RGB skew, the core Joebot glitch technique.

Command truth hierarchy in action. LIVE-VERIFIED forms (GlitchBoard July 2026
sessions + Joe's MTPXControl app and its unit tests) — `verified=True`:

  input skew      W{in}*{r}*{g}*{b}Iseq        (each 0-31, CRLF-terminated)
  reset input skew W{in}*0*0*0Iseq             (clean signal, no glitch)
  output peaking   W{out}*{0|1}Opek
  preset recall    {N}.                         (universal Extron)

DOC-ONLY forms (docs/reference/Extron_SIS_Reference.md, not bench-tested on
these units yet) — `verified=False`: crosspoint ties, system status.

Two realities that shaped this adapter:
  • The MTPX is often in NO-RESPONSE mode — a successful skew send returns
    nothing. So skew/peaking go through the best-effort batch path: the send
    SUCCEEDING (write completed) is the success signal, not a reply. When the
    device DOES echo (`Iseq{in} {r} {g} {b}`), the state is upgraded from
    inferred to confirmed.
  • Skew is per-INPUT. On the MTPX Plus 128 (= 12 in × 8 out) only inputs
    5-12 accept skew; 1-4 are VGA/analog pass-through. Which inputs skew is a
    topology concern owned by the client (GlitchBoard's MTPXTopology); this
    adapter accepts 1-16 and lets the unit reject what it can't do.
"""

from __future__ import annotations

import re

from ..transports import TransportError
from .base import ActionResult, ActionSpec, InvalidParams
from .extron_sis import ExtronSISAdapter

_ISEQ_ECHO_RE = re.compile(r"Iseq\s*(\d+)\D+(\d+)\D+(\d+)\D+(\d+)")
_OPEK_ECHO_RE = re.compile(r"Ope\s*(\d+)\D+(\d+)")
_RPR_ECHO_RE = re.compile(r"Rpr\s*0*(\d+)")
_SPR_ECHO_RE = re.compile(r"Spr\s*0*(\d+)")

_SKEW = {"type": "int", "range": (0, 31), "required": True}


class MTPXAdapter(ExtronSISAdapter):
    device_type = "mtpx"

    actions = {
        "set_input_skew": ActionSpec(
            summary="RGB skew one input (`W{in}*{r}*{g}*{b}Iseq`, each 0-31) — the chromatic-aberration glitch",
            params={
                "input": {"type": "int", "range": (1, 16), "required": True},
                "r": _SKEW, "g": _SKEW, "b": _SKEW,
            },
        ),
        "set_input_skew_batch": ActionSpec(
            summary="RGB skew many inputs in ONE connection — performance path. "
                    "channels: [{input, r, g, b}, …]",
            params={"channels": {"type": "list", "required": True}},
        ),
        "reset_input_skew": ActionSpec(
            summary="Zero an input's skew back to clean (`W{in}*0*0*0Iseq`)",
            params={"input": {"type": "int", "range": (1, 16), "required": True}},
        ),
        "set_output_peaking": ActionSpec(
            summary="Output pre-peaking on/off (`W{out}*{0|1}Opek`) — VHS brightness overdrive",
            params={
                "output": {"type": "int", "range": (1, 16), "required": True},
                "enabled": {"type": "int", "range": (0, 1), "required": True},
            },
        ),
        "recall_preset": ActionSpec(
            summary="Recall preset N (universal Extron `N.`)",
            params={"preset": {"type": "int", "range": (1, 32), "required": True}},
        ),
        "save_preset": ActionSpec(
            summary="SAVE current ties as preset N (`{N},` — comma, the opposite "
                    "of recall's dot). Overwrites preset N; a saved tie set IS a "
                    "lane configuration (wall design doc §1)",
            params={"preset": {"type": "int", "range": (1, 32), "required": True}},
            verified=False,
        ),
        "tie": ActionSpec(
            summary="Route input to output, all signal types (`{in}*{out}!`)",
            params={
                "input": {"type": "int", "range": (0, 16), "required": True},
                "output": {"type": "int", "range": (1, 16), "required": True},
            },
            verified=False,
        ),
        "query_system_status": ActionSpec(
            summary="Voltages / temperature / fan speeds (`S`) — for health display",
            verified=False,
        ),
        "query_firmware": ActionSpec(summary="Query firmware version (`Q`)"),
        "query_part_number": ActionSpec(summary="Query part number (`N`)"),
    }

    # MTPX is CRLF-terminated (verified against MTPXControl).
    async def _batch(self, wires: list[str]) -> ActionResult:
        """Best-effort multi-command send. ok=True when the write completes,
        even if the device (in no-response mode) stays silent."""
        try:
            reply = await self.transport.exchange_batch(wires, terminator="\r\n")
        except TransportError as exc:
            return ActionResult(ok=False, error=str(exc))
        return ActionResult(ok=True, response=reply.response, latency_ms=reply.latency_ms)

    async def do_set_input_skew(self, input: int, r: int, g: int, b: int) -> ActionResult:
        return await self._skew_channels([(input, r, g, b)])

    async def do_set_input_skew_batch(self, channels: list) -> ActionResult:
        parsed: list[tuple[int, int, int, int]] = []
        for i, ch in enumerate(channels):
            if not isinstance(ch, dict):
                raise InvalidParams(f"channels[{i}] must be an object")
            try:
                inp = int(ch["input"]); r = int(ch["r"]); g = int(ch["g"]); b = int(ch["b"])
            except (KeyError, TypeError, ValueError):
                raise InvalidParams(f"channels[{i}] needs integer input, r, g, b") from None
            if not (1 <= inp <= 16 and all(0 <= v <= 31 for v in (r, g, b))):
                raise InvalidParams(f"channels[{i}] out of range (input 1-16, rgb 0-31)")
            parsed.append((inp, r, g, b))
        return await self._skew_channels(parsed)

    async def _skew_channels(self, channels: list[tuple[int, int, int, int]]) -> ActionResult:
        wires = [f"W{inp}*{r}*{g}*{b}Iseq" for inp, r, g, b in channels]
        result = await self._batch(wires)
        if not result.ok:
            return result
        echoed = {int(m.group(1)): (int(m.group(2)), int(m.group(3)), int(m.group(4)))
                  for m in _ISEQ_ECHO_RE.finditer(result.response)}
        state = {f"input_{inp}_skew": [r, g, b] for inp, r, g, b in channels}
        result.state = state
        # Confirmed only if every channel echoed back matching; otherwise the
        # send succeeded but the device stayed silent (no-response mode).
        confirmed = all(echoed.get(inp) == (r, g, b) for inp, r, g, b in channels)
        result.state_source = "command_ack" if (echoed and confirmed) else "inferred"
        return result

    async def do_reset_input_skew(self, input: int) -> ActionResult:
        return await self._skew_channels([(input, 0, 0, 0)])

    async def do_set_output_peaking(self, output: int, enabled: int) -> ActionResult:
        result = await self._batch([f"W{output}*{enabled}Opek"])
        if result.ok:
            result.state = {f"output_{output}_peaking": bool(enabled)}
            echo = _OPEK_ECHO_RE.search(result.response)
            confirmed = echo and int(echo.group(1)) == output and int(echo.group(2)) == enabled
            result.state_source = "command_ack" if confirmed else "inferred"
        return result

    async def do_recall_preset(self, preset: int) -> ActionResult:
        result = await self._batch([f"{preset}."])
        if result.ok:
            result.state = {"preset": preset}
            echo = _RPR_ECHO_RE.search(result.response)
            confirmed = echo and int(echo.group(1)) == preset
            result.state_source = "command_ack" if confirmed else "inferred"
        return result

    def parse_unsolicited(self, line: str) -> dict:
        """Skew echoes (`IseqNN r g b`) arriving outside an exchange — another
        session (GlitchBoard direct, GlitchBeat) or the front panel moved it."""
        if match := _ISEQ_ECHO_RE.match(line):
            inp, r, g, b = (int(match.group(i)) for i in range(1, 5))
            return {f"input_{inp}_skew": [r, g, b]}
        return super().parse_unsolicited(line)

    async def do_save_preset(self, preset: int) -> ActionResult:
        result = await self._batch([f"{preset},"])
        if result.ok:
            echo = _SPR_ECHO_RE.search(result.response)
            confirmed = echo and int(echo.group(1)) == preset
            result.state_source = "command_ack" if confirmed else "inferred"
        return result

    async def do_tie(self, input: int, output: int) -> ActionResult:
        result = await self._batch([f"{input}*{output}!"])
        if result.ok:
            result.state = {f"output_{output}": input}
        return result

    async def do_query_system_status(self) -> ActionResult:
        # `S` gets a real reply, so the strict single-exchange path is right.
        return await self.send("S")

    class Simulator(ExtronSISAdapter.Simulator):
        """Fake MTPX Plus. Echoes skew/peaking like a unit in response mode so the
        confirmation path is exercised; falls back to universal SIS for Q/N/preset."""
        banner = "(c) Copyright 2024, Extron Electronics, MTPX Plus 1616, V1.04, 60-0000-15"

        def __init__(self) -> None:
            super().__init__()
            self.skew: dict[int, tuple[int, int, int]] = {}
            self.peaking: dict[int, int] = {}
            self.ties: dict[int, int] = {}

        def respond(self, command: str) -> str:
            if m := re.fullmatch(r"W(\d{1,2})\*(\d{1,2})\*(\d{1,2})\*(\d{1,2})Iseq", command):
                inp, r, g, b = (int(x) for x in m.groups())
                if not (1 <= inp <= 16 and all(0 <= v <= 31 for v in (r, g, b))):
                    return "E13"
                self.skew[inp] = (r, g, b)
                return f"Iseq{inp:02d} {r:02d} {g:02d} {b:02d}"
            if m := re.fullmatch(r"W(\d{1,2})\*([01])Opek", command):
                out, s = int(m.group(1)), int(m.group(2))
                if not 1 <= out <= 16:
                    return "E12"
                self.peaking[out] = s
                return f"Ope{out:02d} {s}"
            if m := re.fullmatch(r"(\d{1,2})\*(\d{1,2})!", command):
                inp, out = int(m.group(1)), int(m.group(2))
                if not (0 <= inp <= 16 and 1 <= out <= 16):
                    return "E01"
                self.ties[out] = inp
                return f"Out{out:02d} In{inp:02d} All"
            if m := re.fullmatch(r"(\d{1,2}),", command):
                n = int(m.group(1))
                if not 1 <= n <= 32:
                    return "E11"
                return f"Spr{n:02d}"
            if command == "S":
                return "+3.28 +4.98 -5.01 +11.52 -12.35 +86.88 03590 03668 03668"
            return super().respond(command)
