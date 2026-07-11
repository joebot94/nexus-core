"""Groups and scenes — one action fanned to many devices, and ordered
cross-device recalls (the "normal" baseline + its chaos deltas).

- A **group** is a named alias for a set of device targets (`group.wall`).
  Posting one action to a group fans it to every member.
- A **scene** is a named, ordered list of steps; each step targets a device
  OR a group and carries an action + parameters. Recalling a scene runs its
  steps in order, expanding groups, through the same adapter path a single
  `/actions` call uses. The MTPX wall's "normal" baseline is scene #1; chaos
  modes are scenes that layer deltas on top (see docs/MTPX-WALL-DESIGN.md §5).

Persisted as `data/jbt/scenes.jbt` (jbt_type `nexus_scenes`). Hand-editable and
reloadable, exactly like the device registry — malformed entries are skipped
with a warning, never fatal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import jbt


class Group(BaseModel):
    id: str
    label: str = ""
    targets: list[str] = Field(default_factory=list)


class SceneStep(BaseModel):
    target: str                                   # a device_id or a group id
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class Scene(BaseModel):
    id: str
    label: str = ""
    notes: str = ""
    steps: list[SceneStep] = Field(default_factory=list)


# Minimal, honest defaults. The wall baseline recalls the MGP's clean 2×2
# layout (verified); the cross-device MTPX/matrix/SMX steps are authored once
# their commands clear the bench pass (design doc §7), or generated from a
# WallPlan. Kept small so a first run has something real to fan out and recall.
DEFAULT_GROUPS: list[dict[str, Any]] = [
    {"id": "group.mgps", "label": "All MGP scalers", "targets": ["device.mgp.1"]},
    {"id": "group.wall", "label": "Wall devices",
     "targets": ["device.mgp.1", "device.matrix.main", "device.smx.main",
                 "device.dms.main"]},
]

DEFAULT_SCENES: list[dict[str, Any]] = [
    {
        "id": "scene.baseline",
        "label": "Normal baseline",
        "notes": "The known-good reference all fuckery deviates from and "
                 "returns to. MGP clean 2×2 (preset 48, verified). Add MTPX "
                 "tie/skew-0 + matrix/SMX identity steps as they clear the "
                 "bench, or regenerate from a WallPlan.",
        "steps": [
            {"target": "device.mgp.1", "action": "recall_preset",
             "parameters": {"preset": 48}, "note": "clean 2×2 layout"},
        ],
    },
]


class SceneStore:
    """Loads/persists groups + scenes and resolves them against the registry."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.groups: dict[str, Group] = {}
        self.scenes: dict[str, Scene] = {}
        self.load_warnings: list[str] = self.load()

    def load(self) -> list[str]:
        if not self.path.exists():
            doc = jbt.new("nexus_scenes",
                          {"groups": DEFAULT_GROUPS, "scenes": DEFAULT_SCENES},
                          name="Nexus groups & scenes")
            jbt.save(self.path, doc)
        doc = jbt.load(self.path)
        payload = doc.get("payload", {})
        warnings: list[str] = []
        self.groups.clear()
        self.scenes.clear()
        for raw in payload.get("groups", []):
            try:
                group = Group(**raw)
            except Exception as exc:
                warnings.append(f"skipped malformed group {raw.get('id', '?')!r}: {exc}")
                continue
            self.groups[group.id] = group
        for raw in payload.get("scenes", []):
            try:
                scene = Scene(**raw)
            except Exception as exc:
                warnings.append(f"skipped malformed scene {raw.get('id', '?')!r}: {exc}")
                continue
            self.scenes[scene.id] = scene
        return warnings

    def save(self) -> None:
        doc = jbt.new("nexus_scenes", {
            "groups": [g.model_dump() for g in self.groups.values()],
            "scenes": [s.model_dump() for s in self.scenes.values()],
        }, name="Nexus groups & scenes")
        jbt.save(self.path, doc)

    def resolve_group(self, group_id: str) -> list[str] | None:
        group = self.groups.get(group_id)
        return list(group.targets) if group else None

    def expand(self, scene: Scene) -> list[SceneStep]:
        """Flatten a scene's steps into concrete per-device steps, expanding any
        step whose target is a group into one step per member (order preserved).
        A step targeting an unknown group is dropped (surfaced by callers via
        `unresolved`)."""
        out: list[SceneStep] = []
        for step in scene.steps:
            members = self.resolve_group(step.target)
            if members is None:
                out.append(step)                  # a plain device target
            else:
                for device_id in members:
                    out.append(SceneStep(target=device_id, action=step.action,
                                         parameters=dict(step.parameters),
                                         note=step.note))
        return out

    def unresolved_targets(self, scene: Scene, known_devices: set[str]) -> list[str]:
        """Targets in the expanded scene that are neither a known device nor a
        group — a dry-run safety check before firing."""
        missing: list[str] = []
        for step in self.expand(scene):
            if step.target not in known_devices and step.target not in self.groups:
                missing.append(step.target)
        return missing

    def upsert_group(self, group: Group) -> None:
        self.groups[group.id] = group
        self.save()

    def upsert_scene(self, scene: Scene) -> None:
        self.scenes[scene.id] = scene
        self.save()
