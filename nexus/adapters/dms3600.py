"""Extron DMS 3600 adapter (36 in × 24 out digital media switcher).

Wire strings per the deployed joebot-lab `dms_control.py` (which polls the
real unit at 10.0.0.13): tie `{in}*{out}!`, preset recall `{n}.`.
"""

from __future__ import annotations

import re

from .base import ActionResult, ActionSpec
from .extron_sis import ExtronSISAdapter

_TIE_QUERY_RE = re.compile(r"(?:In\s*)?(\d{1,2})", re.IGNORECASE)


class DMS3600Adapter(ExtronSISAdapter):
    device_type = "dms3600"

    actions = {
        "recall_preset": ActionSpec(
            summary="Recall preset N (universal Extron `N.`)",
            params={"preset": {"type": "int", "range": (1, 32), "required": True}},
        ),
        "tie": ActionSpec(
            summary="Tie input to output (`in*out!`)",
            params={
                "input": {"type": "int", "range": (1, 36), "required": True},
                "output": {"type": "int", "range": (1, 24), "required": True},
            },
        ),
        "untie": ActionSpec(
            summary="Untie an output (`0*out!`)",
            params={"output": {"type": "int", "range": (1, 24), "required": True}},
        ),
        "query_tie": ActionSpec(
            summary="Query which input feeds an output (`out!`)",
            params={"output": {"type": "int", "range": (1, 24), "required": True}},
        ),
        "query_firmware": ActionSpec(summary="Query firmware version (`Q`)"),
        "query_part_number": ActionSpec(summary="Query part number (`N`)"),
    }

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
        banner = "(c) Copyright 2024, Extron Electronics, DMS 3600, V1.08, 60-0000-13"

        def __init__(self) -> None:
            super().__init__()
            self.ties: dict[int, int] = {}

        def respond(self, command: str) -> str:
            if match := re.fullmatch(r"(\d{1,2})\*(\d{1,2})!", command):
                inp, out = int(match.group(1)), int(match.group(2))
                if not (0 <= inp <= 36 and 1 <= out <= 24):
                    return "E01"
                self.ties[out] = inp
                return f"Out{out:02d} In{inp:02d} All"
            if match := re.fullmatch(r"(\d{1,2})!", command):
                out = int(match.group(1))
                if not 1 <= out <= 24:
                    return "E12"
                return f"{self.ties.get(out, 0):02d}"
            return super().respond(command)
