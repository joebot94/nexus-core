"""Device adapter interface.

An adapter owns: which normalized actions a device supports, how each
translates to wire protocol, how replies parse back into normalized results,
and which confirmed state changes an acknowledged command implies.

Clients never see wire strings — they send `{"target", "action", "parameters"}`
and get a normalized result. A guarded raw endpoint exists for diagnostics
only (see api/routes.py).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


class UnsupportedAction(Exception):
    pass


class InvalidParams(Exception):
    pass


@dataclass
class ActionSpec:
    """Declares one normalized action: its parameters, safety, and provenance."""
    summary: str
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Destructive actions (device resets, preset overwrites) require an explicit
    # confirm flag and must never fire from automation. None exposed in v1.
    destructive: bool = False
    # True = verified against live hardware; False = manual-derived, needs a
    # bench test before it can be trusted. Surfaced in /capabilities.
    verified: bool = True


@dataclass
class ActionResult:
    ok: bool
    response: str = ""
    error: str | None = None
    latency_ms: int = 0
    # Confirmed state changes implied by the parsed acknowledgment. Empty when
    # the command was sent but nothing was positively confirmed — never claim
    # state changed just because a command went out.
    state: dict[str, Any] = field(default_factory=dict)
    # Provenance for those state values: "command_ack" for set-ack parses,
    # "query" when the action only read the device.
    state_source: str = "command_ack"


class DeviceAdapter:
    device_type = "generic"
    actions: dict[str, ActionSpec] = {}
    # A stable, UI-facing description of the physical shape of the device.
    # It is deliberately separate from `actions`: an action says what a device
    # can do, while a hardware profile says what is installed right now.  An
    # adapter may replace the configured fallback with a read-only hardware
    # discovery result once its model-specific query has been bench-verified.
    profile_defaults: dict[str, Any] = {}

    def __init__(self, config, transport) -> None:
        self.config = config
        self.transport = transport
        # Subclasses refine parameter ranges per installed hardware. Never
        # mutate the class-level action table or another device could inherit a
        # different rack's limits.
        self.actions = copy.deepcopy(self.actions)

    def hardware_profile(self) -> dict[str, Any]:
        """Return the best known physical profile without touching hardware.

        Registry-configured values are an honest fallback while a device is
        offline or while a particular model's discovery query is unverified.
        Consumers must inspect `source` rather than mistaking this for a live
        readback.
        """
        profile = copy.deepcopy(self.profile_defaults)
        configured = getattr(self.config, "hardware_profile", {}) or {}
        for key, value in configured.items():
            # Profiles intentionally stay JSON-shaped, so replacing a nested
            # list such as installed SMX planes is safer than a clever merge.
            profile[key] = copy.deepcopy(value)
        profile.setdefault("kind", "generic")
        profile.setdefault("source", "configured")
        profile.setdefault("input_presence", "unsupported")
        profile.setdefault("label_readback", "unsupported")
        profile.setdefault("notes", "")
        return profile

    def _set_action_range(self, action: str, parameter: str, upper: int) -> None:
        """Constrain an action to the installed profile for this one device."""
        spec = self.actions.get(action)
        if spec and parameter in spec.params:
            rules = spec.params[parameter]
            lower = rules.get("range", (1, upper))[0]
            rules["range"] = (lower, upper)

    def capabilities(self) -> dict[str, Any]:
        return {
            "device_type": self.device_type,
            "hardware_profile": self.hardware_profile(),
            "actions": [
                {
                    "action": name,
                    "summary": spec.summary,
                    "params": spec.params,
                    "destructive": spec.destructive,
                    "verified": spec.verified,
                }
                for name, spec in self.actions.items()
            ],
        }

    async def execute(self, action: str, params: dict[str, Any]) -> ActionResult:
        spec = self.actions.get(action)
        if spec is None:
            raise UnsupportedAction(f"{self.device_type} does not support action '{action}'")
        clean = self._validate(spec, params or {})
        handler = getattr(self, f"do_{action}")
        return await handler(**clean)

    async def probe(self) -> ActionResult:
        """Read-only reachability + identity check. Must never mutate state."""
        raise NotImplementedError

    def parse_unsolicited(self, line: str) -> dict[str, Any]:
        """Map one unsolicited line (what an open session hears when the front
        panel or another session changes something) to confirmed state values.

        Conservative by contract: return {} for anything not positively
        recognized. Which lines devices actually volunteer is bench-truth —
        patterns here reuse the ack shapes until the live listening pass
        confirms them.
        """
        return {}

    @staticmethod
    def _validate(spec: ActionSpec, params: dict[str, Any]) -> dict[str, Any]:
        clean: dict[str, Any] = {}
        for name, rules in spec.params.items():
            if name not in params:
                if rules.get("required", False):
                    raise InvalidParams(f"missing required parameter '{name}'")
                if "default" in rules:
                    clean[name] = rules["default"]
                continue
            value = params[name]
            if rules.get("type") == "int":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    raise InvalidParams(f"parameter '{name}' must be an integer") from None
                lo, hi = rules.get("range", (None, None))
                if lo is not None and not (lo <= value <= hi):
                    raise InvalidParams(f"parameter '{name}' must be in range {lo}-{hi}")
            elif "enum" in rules:
                value = str(value)
                if value not in rules["enum"]:
                    raise InvalidParams(
                        f"parameter '{name}' must be one of: {', '.join(rules['enum'])}")
            elif rules.get("type") == "list":
                # Pass a list through; the handler validates each item (used for
                # batch actions like MTPX multi-channel skew).
                if not isinstance(value, list):
                    raise InvalidParams(f"parameter '{name}' must be a list")
                if rules.get("required") and not value:
                    raise InvalidParams(f"parameter '{name}' must not be empty")
            clean[name] = value
        unknown = set(params) - set(spec.params)
        if unknown:
            raise InvalidParams(f"unknown parameter(s): {', '.join(sorted(unknown))}")
        return clean

    class Simulator:
        """Per-adapter fake device for SimTransport. Subclasses override."""
        banner = ""

        def respond(self, command: str) -> str:  # pragma: no cover - interface
            return "E10"
