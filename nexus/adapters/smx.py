"""Extron SMX System Matrix adapter (16×16, four signal planes).

Wire strings per the deployed joebot-lab `smx_control.py` — the module whose
tie/preset syntax was corrected against SIS reality in July 2026:

  preset recall is `Rpr{nn}` (NOT the universal `{n}.` — the SMX rejects it),
  preset save `Spr{nn}`, ties are plane-prefixed `{plane}*{in}*{out}{signal}`
  where signal is `&` for the video planes and `$` for audio, tie query is
  `{plane}*{out}!`.

Planes: 00 VGA · 01 S-Video · 02 Video · 04 Audio. May prompt for a
password on connect — the transport answers it.
"""

from __future__ import annotations

import re

from .base import ActionResult, ActionSpec
from .extron_sis import ExtronSISAdapter

PLANES = {"00": "&", "01": "&", "02": "&", "04": "$"}
PLANE_ORDER = ["00", "01", "02", "04"]
_TIE_QUERY_RE = re.compile(r"(?:In\s*)?(\d{1,2})", re.IGNORECASE)

_PLANE_PARAM = {"enum": PLANE_ORDER, "required": False, "default": "00"}


class SMXAdapter(ExtronSISAdapter):
    device_type = "smx"
    profile_defaults = {
        "kind": "multiplane_matrix",
        "inputs": 16,
        "outputs": 16,
        "planes": [
            {"id": "00", "label": "VGA", "signal": "video", "tie_suffix": "&", "installed": True},
            {"id": "01", "label": "S-Video", "signal": "video", "tie_suffix": "&", "installed": True},
            {"id": "02", "label": "Video", "signal": "video", "tie_suffix": "&", "installed": True},
            {"id": "04", "label": "Audio", "signal": "audio", "tie_suffix": "$", "installed": True},
        ],
        "input_presence": "supported_pending_query_validation",
        "label_readback": "unknown",
        "notes": "Current installed card planes; future installed planes extend this list.",
    }

    actions = {
        "recall_preset": ActionSpec(
            summary="Recall global preset N (`RprNN` — SMX rejects the universal `N.`)",
            params={"preset": {"type": "int", "range": (1, 32), "required": True}},
        ),
        "tie": ActionSpec(
            summary="Tie input to output on one plane (`PP*in*out&`, `$` on audio)",
            params={
                "input": {"type": "int", "range": (0, 16), "required": True},
                "output": {"type": "int", "range": (1, 16), "required": True},
                "plane": _PLANE_PARAM,
            },
        ),
        "tie_all_planes": ActionSpec(
            summary="Tie input to output on all four planes (VGA/S-Video/Video/Audio)",
            params={
                "input": {"type": "int", "range": (0, 16), "required": True},
                "output": {"type": "int", "range": (1, 16), "required": True},
            },
        ),
        "query_tie": ActionSpec(
            summary="Query which input feeds an output on a plane (`PP*out!`)",
            params={
                "output": {"type": "int", "range": (1, 16), "required": True},
                "plane": _PLANE_PARAM,
            },
        ),
        "query_firmware": ActionSpec(summary="Query firmware version (`Q`)"),
        "query_part_number": ActionSpec(summary="Query part number (`N`)"),
    }

    def __init__(self, config, transport) -> None:
        super().__init__(config, transport)
        profile = self.hardware_profile()
        planes = [p for p in profile.get("planes", []) if p.get("installed", True)]
        self.plane_suffixes = {str(p["id"]): str(p.get("tie_suffix", "&")) for p in planes if p.get("id")}
        # Preserve the known working four-plane fallback if a legacy registry
        # omits planes. A future card becomes data, not a Swift/Python rewrite.
        if not self.plane_suffixes:
            self.plane_suffixes = dict(PLANES)
        self.plane_order = list(self.plane_suffixes)
        self._set_action_range("tie", "input", int(profile.get("inputs", 16)))
        self._set_action_range("tie", "output", int(profile.get("outputs", 16)))
        self._set_action_range("tie_all_planes", "input", int(profile.get("inputs", 16)))
        self._set_action_range("tie_all_planes", "output", int(profile.get("outputs", 16)))
        self._set_action_range("query_tie", "output", int(profile.get("outputs", 16)))
        for action in ("tie", "query_tie"):
            self.actions[action].params["plane"]["enum"] = self.plane_order
            self.actions[action].params["plane"]["default"] = self.plane_order[0]

    async def do_recall_preset(self, preset: int) -> ActionResult:
        result = await self.send(f"Rpr{preset:02d}")
        if result.ok:
            # The lab module doesn't parse a structured ack here; confirm only
            # if the echo carries the preset number back.
            if re.search(rf"(?:Rpr|Gpr)\s*0*{preset}\b", result.response):
                result.state = {"preset": preset}
        return result

    async def do_tie(self, input: int, output: int, plane: str = "00") -> ActionResult:
        result = await self.send(f"{plane}*{input}*{output}{self.plane_suffixes[plane]}")
        if result.ok:
            result.state = {f"plane_{plane}_output_{output}": input}
        return result

    async def do_tie_all_planes(self, input: int, output: int) -> ActionResult:
        # One exchange per plane, mirroring the lab's send_tie_global. A single
        # pooled connection for the four writes is an M4 optimization.
        last = ActionResult(ok=True)
        state: dict[str, int] = {}
        total_ms = 0
        for plane in self.plane_order:
            last = await self.send(f"{plane}*{input}*{output}{self.plane_suffixes[plane]}")
            total_ms += last.latency_ms
            if not last.ok:
                last.latency_ms = total_ms
                return last
            state[f"plane_{plane}_output_{output}"] = input
        last.state = state
        last.latency_ms = total_ms
        return last

    async def do_query_tie(self, output: int, plane: str = "00") -> ActionResult:
        result = await self.send(f"{plane}*{output}!")
        if result.ok:
            match = _TIE_QUERY_RE.search(result.response)
            if match:
                result.state = {f"plane_{plane}_output_{output}": int(match.group(1))}
                result.state_source = "query"
        return result

    class Simulator(ExtronSISAdapter.Simulator):
        banner = "(c) Copyright 2024, Extron Electronics, SMX System MultiMatrix, V1.24, 60-0000-11"

        def __init__(self) -> None:
            super().__init__()
            self.ties: dict[tuple[str, int], int] = {}

        def respond(self, command: str) -> str:
            if match := re.fullmatch(r"Rpr(\d{1,2})", command):
                preset = int(match.group(1))
                if not 1 <= preset <= 32:
                    return "E11"
                self.preset = preset
                return f"Rpr{preset:02d}"
            if match := re.fullmatch(r"(\d{2})\*(\d{1,2})\*(\d{1,2})[&$]", command):
                plane, inp, out = match.group(1), int(match.group(2)), int(match.group(3))
                if plane not in PLANES or not (0 <= inp <= 16 and 1 <= out <= 16):
                    return "E13"
                self.ties[(plane, out)] = inp
                return f"In{inp:02d} All"
            if match := re.fullmatch(r"(\d{2})\*(\d{1,2})!", command):
                plane, out = match.group(1), int(match.group(2))
                if plane not in PLANES or not 1 <= out <= 16:
                    return "E12"
                return f"In{self.ties.get((plane, out), 0)} Ao{out}"
            if re.fullmatch(r"\d{1,3}\.", command):
                return "E10"  # the real SMX rejects universal `N.` recall
            return super().respond(command)
