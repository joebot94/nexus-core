"""Extron Matrix 12800 adapter.

Wire strings per the deployed joebot-lab `matrix12800_control.py` (which
polls the real unit at 10.0.0.12): tie `{in}*{out}!`, untie `0*{out}!`,
tie query `{out}!`, preset recall `{n}.`. The device may prompt for a
password on connect (admin/admin) — the transport answers it.
"""

from __future__ import annotations

import re

from .base import ActionResult, ActionSpec
from .extron_sis import ExtronSISAdapter

_TIE_ACK_RE = re.compile(r"Out\s*(\d+)\s*[• ]\s*In\s*(\d+)", re.IGNORECASE)
_TIE_QUERY_RE = re.compile(r"(?:In\s*)?(\d{1,3})", re.IGNORECASE)


class Matrix12800Adapter(ExtronSISAdapter):
    device_type = "matrix12800"
    profile_defaults = {
        "kind": "matrix",
        "inputs": 128,
        "outputs": 128,
        "planes": [{"id": "all", "label": "All signals", "installed": True}],
        "input_presence": "supported_pending_query_validation",
        "label_readback": "unknown",
        "notes": "Configured maximum; replace with read-only chassis discovery when validated.",
    }

    actions = {
        "recall_preset": ActionSpec(
            summary="Recall global preset N (universal Extron `N.`)",
            params={"preset": {"type": "int", "range": (1, 128), "required": True}},
        ),
        "tie": ActionSpec(
            summary="Tie input to output, all signal types (`in*out!`)",
            params={
                "input": {"type": "int", "range": (1, 128), "required": True},
                "output": {"type": "int", "range": (1, 128), "required": True},
            },
        ),
        "untie": ActionSpec(
            summary="Untie an output (`0*out!`)",
            params={"output": {"type": "int", "range": (1, 128), "required": True}},
        ),
        "query_tie": ActionSpec(
            summary="Query which input feeds an output (`out!`)",
            params={"output": {"type": "int", "range": (1, 128), "required": True}},
        ),
        "query_firmware": ActionSpec(summary="Query firmware version (`Q`)"),
        "query_part_number": ActionSpec(summary="Query part number (`N`)"),
    }

    def __init__(self, config, transport) -> None:
        super().__init__(config, transport)
        profile = self.hardware_profile()
        self._set_action_range("tie", "input", int(profile.get("inputs", 128)))
        self._set_action_range("tie", "output", int(profile.get("outputs", 128)))
        self._set_action_range("untie", "output", int(profile.get("outputs", 128)))
        self._set_action_range("query_tie", "output", int(profile.get("outputs", 128)))

    async def do_tie(self, input: int, output: int) -> ActionResult:
        result = await self.send(f"{input}*{output}!")
        if result.ok:
            result.state = {f"output_{output}": input}
        return result

    async def do_untie(self, output: int) -> ActionResult:
        result = await self.send(f"0*{output}!")
        if result.ok:
            result.state = {f"output_{output}": 0}
        return result

    async def do_query_tie(self, output: int) -> ActionResult:
        result = await self.send(f"{output}!")
        if result.ok:
            match = _TIE_QUERY_RE.search(result.response)
            if match:
                result.state = {f"output_{output}": int(match.group(1))}
                result.state_source = "query"
        return result

    class Simulator(ExtronSISAdapter.Simulator):
        banner = "(c) Copyright 2024, Extron Electronics, Matrix 12800, V2.10, 60-0000-12"

        def __init__(self) -> None:
            super().__init__()
            self.ties: dict[int, int] = {}

        def respond(self, command: str) -> str:
            if match := re.fullmatch(r"(\d{1,3})\*(\d{1,3})!", command):
                inp, out = int(match.group(1)), int(match.group(2))
                if not (0 <= inp <= 128 and 1 <= out <= 128):
                    return "E01"
                self.ties[out] = inp
                return f"Out{out:02d} In{inp:02d} All"
            if match := re.fullmatch(r"(\d{1,3})!", command):
                out = int(match.group(1))
                if not 1 <= out <= 128:
                    return "E12"
                return f"{self.ties.get(out, 0):02d}"
            return super().respond(command)
