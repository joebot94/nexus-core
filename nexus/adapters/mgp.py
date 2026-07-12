"""Extron MGP 464 adapter.

Live-verified command set (GlitchBoard sessions, July 2026, MGP 464 Pro DI
@ 10.0.0.63): layout preset recall is `2*NN.` (the `2*` function prefix and
trailing `.` are part of the command) acknowledged `Rpr2*NNN.` zero-padded;
input→window routing is `input*window!`; window query is `window!` → `NN`.
Firmware query `Q`; note this unit rejects `I` with E13 — always use `Q`.

Joe's saved chaos layouts live in preset slots 48–71; 48 is the clean 2×2.
"""

from __future__ import annotations

import re

from .base import ActionResult, ActionSpec
from .extron_sis import ExtronSISAdapter

_RECALL_ACK_RE = re.compile(r"Rpr\s*2\*(\d{1,3})")
_WINDOW_QUERY_RE = re.compile(r"^(\d{1,2})$")


class MGP464Adapter(ExtronSISAdapter):
    device_type = "mgp464"

    actions = {
        "recall_preset": ActionSpec(
            summary="Recall MGP layout preset N (`2*NN.`, ack `Rpr2*NNN.`) — slots 48-71 are the saved 2×2 chaos layouts",
            params={"preset": {"type": "int", "range": (1, 128), "required": True}},
        ),
        "route_input_to_window": ActionSpec(
            summary="Route input to window (`input*window!`)",
            params={
                "input": {"type": "int", "range": (1, 8), "required": True},
                "window": {"type": "int", "range": (1, 4), "required": True},
            },
        ),
        "query_window": ActionSpec(
            summary="Query which input feeds a window (`window!` → input number)",
            params={"window": {"type": "int", "range": (1, 4), "required": True}},
        ),
        "set_window_blank": ActionSpec(
            summary="Blank/unblank a window (`{w}*{0|1}B`) — GlitchWall-verified; "
                    "the FX-chase stutter",
            params={
                "window": {"type": "int", "range": (1, 4), "required": True},
                "on": {"type": "int", "range": (0, 1), "required": True},
            },
        ),
        "set_window_freeze": ActionSpec(
            summary="Freeze/unfreeze a window (`{w}*{0|1}F`) — GlitchWall-verified",
            params={
                "window": {"type": "int", "range": (1, 4), "required": True},
                "on": {"type": "int", "range": (0, 1), "required": True},
            },
        ),
        "query_firmware": ActionSpec(summary="Query firmware version (`Q`)"),
        "query_part_number": ActionSpec(summary="Query part number (`N`)"),
    }

    def parse_unsolicited(self, line: str) -> dict:
        """A front-panel layout recall should broadcast the same `Rpr2*NNN` an
        acked one does. Window-route acks are a bare `NN` — too ambiguous to
        trust unsolicited, so those are deliberately not parsed."""
        if match := _RECALL_ACK_RE.match(line):
            return {"preset": int(match.group(1))}
        return super().parse_unsolicited(line)

    async def do_recall_preset(self, preset: int) -> ActionResult:
        result = await self.send(f"2*{preset}.")
        if result.ok:
            ack = _RECALL_ACK_RE.search(result.response)
            if ack and int(ack.group(1)) == preset:
                result.state = {"preset": preset}
            else:
                result.error = f"unexpected ack: {result.response!r}"
                result.ok = False
        return result

    async def do_route_input_to_window(self, input: int, window: int) -> ActionResult:
        result = await self.send(f"{input}*{window}!")
        if result.ok:
            result.state = {f"window_{window}": input}
        return result

    async def do_set_window_blank(self, window: int, on: int) -> ActionResult:
        return await self._window_fx(window, on, "B", "blank")

    async def do_set_window_freeze(self, window: int, on: int) -> ActionResult:
        return await self._window_fx(window, on, "F", "freeze")

    async def _window_fx(self, window: int, on: int, code: str, key: str) -> ActionResult:
        """`{w}*{0|1}B|F`. The exact ack isn't bench-pinned, so success is a
        non-error reply and the state is set from the command (verified wire,
        best-effort confirm)."""
        result = await self.send(f"{window}*{on}{code}")
        if result.ok:
            result.state = {f"window_{window}_{key}": bool(on)}
        return result

    async def do_query_window(self, window: int) -> ActionResult:
        result = await self.send(f"{window}!")
        if result.ok:
            match = _WINDOW_QUERY_RE.match(result.response)
            if match:
                result.state = {f"window_{window}": int(match.group(1))}
                result.state_source = "query"
        return result

    class Simulator(ExtronSISAdapter.Simulator):
        """Fake MGP 464 matching the recorded live wire behavior."""
        banner = "(c) Copyright 2024, Extron Electronics, MGP 464 DI, V1.12, 60-1076-01"

        def __init__(self) -> None:
            self.preset = 48
            self.windows = {1: 1, 2: 2, 3: 3, 4: 4}

        def respond(self, command: str) -> str:
            if command == "Q":
                return "1.12"
            if command == "N":
                return "60-1076-01"
            if match := re.fullmatch(r"2\*(\d{1,3})\.", command):
                preset = int(match.group(1))
                if not 1 <= preset <= 128:
                    return "E11"
                self.preset = preset
                return f"Rpr2*{preset:03d}"
            if match := re.fullmatch(r"(\d{1,2})\*(\d)!", command):
                inp, win = int(match.group(1)), int(match.group(2))
                if win not in self.windows or not 1 <= inp <= 8:
                    return "E13"
                self.windows[win] = inp
                return f"{inp:02d}"
            if match := re.fullmatch(r"(\d)!", command):
                win = int(match.group(1))
                if win not in self.windows:
                    return "E12"
                return f"{self.windows[win]:02d}"
            if match := re.fullmatch(r"(\d)\*([01])([BF])", command):
                win, state, code = int(match.group(1)), int(match.group(2)), match.group(3)
                if win not in self.windows:
                    return "E12"
                return f"Vfx{win}*{state}{code}"     # non-error ack (exact form bench-TBD)
            return "E10"
