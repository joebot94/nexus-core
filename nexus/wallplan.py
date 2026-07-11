"""MTPX wall cascade planner — the "figure it out once" logic, executable.

Design: docs/MTPX-WALL-DESIGN.md. Pure and deterministic: takes unit specs
plus per-slot cascade requests, allocates ports, validates budgets, and emits
the physical patch list, per-unit tie wires, and Matrix 12800 tie wires.
Fires nothing — the output is planning truth for clients (GlitchBoard's
topology editor, the future graphical wall view) and for the operator racking
the loopback cables.

Vocabulary (matches the design doc):
  slot  — logical wall position ("r1c1" … "r4c4"), what clients speak.
  lane  — one slot's path through one unit: source input → skew passes via
          loopback hops → final output toward the matrix.
  pass  — one trip through a skewable input; each pass adds 0–31 px/channel.

Tie wires emitted here use the SIS form `{in}*{out}!`, which is verified=false
on the MTPX (bench item #1 in the design doc). The plan is safe to generate
and display regardless — it sends nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# in_count, out_count, skewable inputs. Extron model numbering is IN×OUT.
# The 128's inputs 1-4 are VGA/analog pass-through — they route but can't skew.
MODEL_SPECS: dict[str, tuple[int, int, tuple[int, ...]]] = {
    "MTPX Plus 1616": (16, 16, tuple(range(1, 17))),
    "MTPX Plus 128": (12, 8, tuple(range(5, 13))),
    "MTPX Plus 88": (8, 8, tuple(range(1, 9))),
    "MTPX Plus 84": (8, 4, tuple(range(1, 9))),
}

MAX_SKEW_PER_PASS = 31


class WallPlanError(ValueError):
    """A request that cannot be satisfied (unknown model, over budget…)."""


@dataclass(frozen=True)
class UnitSpec:
    """One physical MTPX unit in the cluster."""

    name: str                      # "mtpx1"
    model: str = "MTPX Plus 128"
    host: str = ""                 # "mtpx1.extron.video" (UNCONFIRMED until power-up)

    def spec(self) -> tuple[int, int, tuple[int, ...]]:
        try:
            return MODEL_SPECS[self.model]
        except KeyError:
            raise WallPlanError(f"{self.name}: unknown model {self.model!r}") from None


@dataclass(frozen=True)
class SlotRequest:
    """One wall slot asking for a lane on a unit."""

    slot: str                      # "r1c1"
    unit: str                      # UnitSpec.name
    passes: int = 2                # skew passes wanted (1 = no loopback)


@dataclass
class Lane:
    """A resolved lane: the ports one slot's signal occupies on its unit."""

    slot: str
    unit: str
    inputs: list[int]              # cascade order; inputs[0] is the source input
    outputs: list[int]             # cascade order; outputs[-1] is the final out
    matrix_input: int              # which Matrix 12800 input the final out feeds

    @property
    def passes(self) -> int:
        return len(self.inputs)

    @property
    def max_skew(self) -> int:
        return self.passes * MAX_SKEW_PER_PASS

    @property
    def loopbacks(self) -> list[tuple[int, int]]:
        """Physical patch cables (out, in) this lane needs, cascade order."""
        return list(zip(self.outputs[:-1], self.inputs[1:]))

    def tie_wires(self) -> list[str]:
        """SIS ties forming the lane (`{in}*{out}!` — verified=false on MTPX)."""
        return [f"{i}*{o}!" for i, o in zip(self.inputs, self.outputs)]

    def skew_wires(self, r: int, g: int, b: int) -> list[str]:
        """Per-pass skew wires for a TOTAL per-channel target, greedily split
        across the lane's passes (62 blue over 2 passes → 31 + 31)."""
        parts = zip(distribute_skew(r, self.passes),
                    distribute_skew(g, self.passes),
                    distribute_skew(b, self.passes))
        return [f"W{inp}*{pr}*{pg}*{pb}Iseq"
                for inp, (pr, pg, pb) in zip(self.inputs, parts)]


def distribute_skew(total: int, passes: int) -> list[int]:
    """Split a total per-channel skew across passes, 0-31 each, front-loaded.
    Raises if the lane physically can't reach the total."""
    ceiling = passes * MAX_SKEW_PER_PASS
    if not 0 <= total <= ceiling:
        raise WallPlanError(f"skew {total} out of range for {passes}-pass lane (0-{ceiling})")
    out = []
    for _ in range(passes):
        step = min(total, MAX_SKEW_PER_PASS)
        out.append(step)
        total -= step
    return out


@dataclass
class WallPlan:
    """The resolved wall: lanes in slot order, plus rack-facing artifacts."""

    units: list[UnitSpec]
    lanes: list[Lane]
    warnings: list[str] = field(default_factory=list)

    def lane(self, slot: str) -> Lane:
        for lane in self.lanes:
            if lane.slot == slot:
                return lane
        raise WallPlanError(f"no lane for slot {slot!r}")

    def patch_list(self) -> list[str]:
        """Cable-by-cable loopback patching, for physically racking the wall."""
        lines = []
        for lane in self.lanes:
            for out, inp in lane.loopbacks:
                lines.append(f"{lane.unit}: Out {out} → In {inp}  (loopback, slot {lane.slot})")
        return lines

    def unit_ties(self) -> dict[str, list[str]]:
        """Baseline tie wires per unit — what a unit preset should store."""
        ties: dict[str, list[str]] = {u.name: [] for u in self.units}
        for lane in self.lanes:
            ties[lane.unit].extend(lane.tie_wires())
        return ties

    def matrix_ties(self) -> list[str]:
        """Matrix 12800 baseline: slot k's input tied to output k (identity),
        so MGP⌈k/4⌉ gets its quadrant. `{in}*{out}!`."""
        return [f"{lane.matrix_input}*{k}!" for k, lane in enumerate(self.lanes, start=1)]

    def mgp_assignment(self) -> dict[str, int]:
        """slot → MGP number (4 slots per MGP 464, in slot order)."""
        return {lane.slot: (k - 1) // 4 + 1 for k, lane in enumerate(self.lanes, start=1)}


def plan_wall(units: list[UnitSpec], requests: list[SlotRequest]) -> WallPlan:
    """Allocate every slot's lane onto its unit, first-fit in request order.

    Skewable inputs and outputs are handed out lowest-first per unit; matrix
    inputs are handed out in request (slot) order across the whole wall.
    Raises WallPlanError when a unit's port budget can't carry its slots.
    """
    by_name = {u.name: u for u in units}
    if len(by_name) != len(units):
        raise WallPlanError("duplicate unit names")

    free_inputs: dict[str, list[int]] = {}
    free_outputs: dict[str, list[int]] = {}
    for u in units:
        _ins, outs, skewable = u.spec()
        free_inputs[u.name] = list(skewable)
        free_outputs[u.name] = list(range(1, outs + 1))

    seen_slots: set[str] = set()
    lanes: list[Lane] = []
    warnings: list[str] = []

    for k, req in enumerate(requests, start=1):
        if req.slot in seen_slots:
            raise WallPlanError(f"slot {req.slot!r} requested twice")
        seen_slots.add(req.slot)
        if req.unit not in by_name:
            raise WallPlanError(f"slot {req.slot!r}: unknown unit {req.unit!r}")
        if req.passes < 1:
            raise WallPlanError(f"slot {req.slot!r}: passes must be >= 1")

        ins, outs = free_inputs[req.unit], free_outputs[req.unit]
        if len(ins) < req.passes or len(outs) < req.passes:
            raise WallPlanError(
                f"slot {req.slot!r}: {req.unit} out of ports for a {req.passes}-pass lane "
                f"({len(ins)} skewable inputs, {len(outs)} outputs left)")

        lanes.append(Lane(
            slot=req.slot, unit=req.unit,
            inputs=[ins.pop(0) for _ in range(req.passes)],
            outputs=[outs.pop(0) for _ in range(req.passes)],
            matrix_input=k,
        ))

    if len(lanes) > 16:
        warnings.append(f"{len(lanes)} slots exceeds one Matrix-12800-to-4-MGP wall (16)")
    warnings.append("MTPX ties are verified=false — bench before firing (design doc §7)")

    return WallPlan(units=units, lanes=lanes, warnings=warnings)


def joe_wall(unit_count: int = 5, passes: int = 2) -> WallPlan:
    """The brain-dump wall: N × MTPX Plus 128, 3 slots each, the last unit
    carrying a 4th, filling row-major slots of the 4×4 logical wall."""
    units = [UnitSpec(name=f"mtpx{n}", host=f"mtpx{n}.extron.video")
             for n in range(1, unit_count + 1)]
    requests = []
    slot_index = 0
    for n, unit in enumerate(units, start=1):
        count = 4 if n == unit_count else 3
        for _ in range(count):
            row, col = divmod(slot_index, 4)
            requests.append(SlotRequest(slot=f"r{row + 1}c{col + 1}",
                                        unit=unit.name, passes=passes))
            slot_index += 1
    return plan_wall(units, requests)
