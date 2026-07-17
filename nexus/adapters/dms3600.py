"""Extron DMS 3600 adapter (36 in × 36 out digital media switcher).

Wire strings per the deployed joebot-lab `dms_control.py` (which polls the
real unit at 10.0.0.13): tie `{in}*{out}!`, preset recall `{n}.`.
"""

from __future__ import annotations

import re

from .base import ActionResult, ActionSpec
from .extron_sis import ExtronSISAdapter, name_bank_action

_TIE_QUERY_RE = re.compile(r"(?:In\s*)?(\d{1,2})", re.IGNORECASE)


class DMS3600Adapter(ExtronSISAdapter):
    device_type = "dms3600"
    profile_defaults = {
        "kind": "matrix",
        "inputs": 36,
        "outputs": 36,
        "planes": [{"id": "all", "label": "All signals", "installed": True}],
        "input_presence": "supported_pending_query_validation",
        "label_readback": "unknown",
        "notes": "Installed 36×36 card population; live discovery query still needs verification.",
    }

    actions = {
        "recall_preset": ActionSpec(
            summary="Recall preset N (universal Extron `N.`)",
            params={"preset": {"type": "int", "range": (1, 32), "required": True}},
        ),
        "tie": ActionSpec(
            summary="Tie input to output (`in*out!`)",
            params={
                "input": {"type": "int", "range": (1, 36), "required": True},
                "output": {"type": "int", "range": (1, 36), "required": True},
            },
        ),
        "untie": ActionSpec(
            summary="Untie an output (`0*out!`)",
            params={"output": {"type": "int", "range": (1, 36), "required": True}},
        ),
        "tie_many": ActionSpec(
            summary="Quick multiple tie — all pairs switch as ONE atomic command "
                    "(`in1*out1*in2*out2...!`, ack `Qik`): one switch event and one "
                    "DVI re-handshake instead of a sequential tie per output",
            params={"ties": {"type": "list", "required": True}},
            verified=False,  # doc-only (Extron_SIS_Reference.md); bench-confirm ack + atomicity
        ),
        "query_tie": ActionSpec(
            summary="Query which input feeds an output (`out!`)",
            params={"output": {"type": "int", "range": (1, 36), "required": True}},
        ),
        "query_firmware": ActionSpec(summary="Query firmware version (`Q`)"),
        "query_part_number": ActionSpec(summary="Query part number (`N`)"),
        "read_name_bank": name_bank_action(["input", "output", "preset"]),
    }

    def __init__(self, config, transport) -> None:
        super().__init__(config, transport)
        profile = self.hardware_profile()
        self._set_action_range("tie", "input", int(profile.get("inputs", 36)))
        self._set_action_range("tie", "output", int(profile.get("outputs", 36)))
        self._set_action_range("untie", "output", int(profile.get("outputs", 36)))
        self._set_action_range("query_tie", "output", int(profile.get("outputs", 36)))

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

    async def do_tie_many(self, ties: list) -> ActionResult:
        profile = self.hardware_profile()
        pairs = self.parse_tie_pairs(ties, max_input=int(profile.get("inputs", 36)),
                                     max_output=int(profile.get("outputs", 36)))
        wire = "*".join(f"{inp}*{out}" for inp, out in pairs) + "!"
        result = await self.send(wire)
        if result.ok:
            result.state = {f"output_{out}": inp for inp, out in pairs}
        return result

    async def do_query_tie(self, output: int) -> ActionResult:
        result = await self.send(f"{output}!")
        if result.ok:
            match = _TIE_QUERY_RE.search(result.response)
            if match:
                result.state = {f"output_{output}": int(match.group(1))}
                result.state_source = "query"
        return result

    async def do_read_name_bank(self, kind: str, start: int = 1, count: int = 32) -> ActionResult:
        profile = self.hardware_profile()
        return await self.read_name_bank(kind, start, count, {
            "input": int(profile.get("inputs", 36)),
            "output": int(profile.get("outputs", 36)),
            "preset": int(profile.get("presets", 32)),
        })

    class Simulator(ExtronSISAdapter.Simulator):
        banner = "(c) Copyright 2024, Extron Electronics, DMS 3600, V1.08, 60-0000-13"

        def __init__(self) -> None:
            super().__init__()
            self.ties: dict[int, int] = {}

        def respond(self, command: str) -> str:
            if re.fullmatch(r"\d{1,2}\*\d{1,2}(?:\*\d{1,2}\*\d{1,2})+!", command):
                nums = [int(n) for n in command[:-1].split("*")]
                pairs = list(zip(nums[::2], nums[1::2]))
                if any(not (0 <= inp <= 36 and 1 <= out <= 36) for inp, out in pairs):
                    return "E01"
                for inp, out in pairs:
                    self.ties[out] = inp
                return "Qik"
            if match := re.fullmatch(r"(\d{1,2})\*(\d{1,2})!", command):
                inp, out = int(match.group(1)), int(match.group(2))
                if not (0 <= inp <= 36 and 1 <= out <= 36):
                    return "E01"
                self.ties[out] = inp
                return f"Out{out:02d} In{inp:02d} All"
            if match := re.fullmatch(r"(\d{1,2})!", command):
                out = int(match.group(1))
                if not 1 <= out <= 36:
                    return "E12"
                return f"{self.ties.get(out, 0):02d}"
            return super().respond(command)
