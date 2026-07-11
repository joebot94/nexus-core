"""Wall cascade planner — port budgets, patching, tie/skew wire generation."""

import pytest

from nexus.wallplan import (
    Lane, SlotRequest, UnitSpec, WallPlanError,
    distribute_skew, joe_wall, plan_wall,
)


def _unit(name="mtpx1", model="MTPX Plus 128"):
    return UnitSpec(name=name, model=model)


# ---- distribute_skew -------------------------------------------------------

def test_distribute_skew_greedy_front_load():
    assert distribute_skew(62, 2) == [31, 31]
    assert distribute_skew(40, 2) == [31, 9]
    assert distribute_skew(0, 3) == [0, 0, 0]
    assert distribute_skew(31, 1) == [31]


def test_distribute_skew_rejects_unreachable_totals():
    with pytest.raises(WallPlanError):
        distribute_skew(63, 2)
    with pytest.raises(WallPlanError):
        distribute_skew(-1, 2)


# ---- single-unit budgets ---------------------------------------------------

def test_128_carries_three_two_pass_lanes_with_room_for_a_fourth():
    # The brain-dump claim: a 128 does 3 sources, maybe a 4th. 4 × 2-pass = 8/8.
    reqs = [SlotRequest(slot=f"r1c{c}", unit="mtpx1", passes=2) for c in range(1, 5)]
    plan = plan_wall([_unit()], reqs)
    assert len(plan.lanes) == 4
    used_inputs = [i for lane in plan.lanes for i in lane.inputs]
    assert sorted(used_inputs) == list(range(5, 13))  # only skewable inputs 5-12
    used_outputs = [o for lane in plan.lanes for o in lane.outputs]
    assert sorted(used_outputs) == list(range(1, 9))


def test_128_refuses_a_fifth_two_pass_lane():
    reqs = [SlotRequest(slot=f"s{i}", unit="mtpx1", passes=2) for i in range(5)]
    with pytest.raises(WallPlanError, match="out of ports"):
        plan_wall([_unit()], reqs)


def test_monster_lane_uses_the_whole_unit():
    plan = plan_wall([_unit()], [SlotRequest(slot="r1c1", unit="mtpx1", passes=8)])
    lane = plan.lane("r1c1")
    assert lane.max_skew == 248
    assert len(lane.loopbacks) == 7


def test_input_validation():
    with pytest.raises(WallPlanError, match="requested twice"):
        plan_wall([_unit()], [SlotRequest(slot="a", unit="mtpx1"),
                              SlotRequest(slot="a", unit="mtpx1")])
    with pytest.raises(WallPlanError, match="unknown unit"):
        plan_wall([_unit()], [SlotRequest(slot="a", unit="nope")])
    with pytest.raises(WallPlanError, match="unknown model"):
        plan_wall([_unit(model="MTPX Plus 9000")],
                  [SlotRequest(slot="a", unit="mtpx1")])
    with pytest.raises(WallPlanError, match="passes"):
        plan_wall([_unit()], [SlotRequest(slot="a", unit="mtpx1", passes=0)])


# ---- lane wire generation --------------------------------------------------

def test_lane_ties_loopbacks_and_skew_wires():
    plan = plan_wall([_unit()], [SlotRequest(slot="r1c1", unit="mtpx1", passes=2)])
    lane = plan.lane("r1c1")
    # First-fit: inputs 5,6; outputs 1,2. Signal: in5 → out1 → cable → in6 → out2.
    assert lane.inputs == [5, 6]
    assert lane.outputs == [1, 2]
    assert lane.loopbacks == [(1, 6)]
    assert lane.tie_wires() == ["5*1!", "6*2!"]
    assert lane.skew_wires(0, 0, 62) == ["W5*0*0*31Iseq", "W6*0*0*31Iseq"]
    assert lane.skew_wires(10, 0, 40) == ["W5*10*0*31Iseq", "W6*0*0*9Iseq"]


# ---- the brain-dump wall ---------------------------------------------------

def test_joe_wall_is_sixteen_slots_across_five_128s():
    plan = joe_wall()
    assert len(plan.lanes) == 16
    assert [u.name for u in plan.units] == [f"mtpx{n}" for n in range(1, 6)]
    assert plan.units[0].host == "mtpx1.extron.video"
    # 3 slots per unit, the last unit carries the 4th.
    per_unit = {u.name: sum(1 for l in plan.lanes if l.unit == u.name) for u in plan.units}
    assert per_unit == {"mtpx1": 3, "mtpx2": 3, "mtpx3": 3, "mtpx4": 3, "mtpx5": 4}
    # Slots are row-major over the 4×4 wall and matrix inputs follow slot order.
    assert plan.lanes[0].slot == "r1c1"
    assert plan.lanes[15].slot == "r4c4"
    assert [l.matrix_input for l in plan.lanes] == list(range(1, 17))


def test_plan_from_registry_reads_wall_metadata():
    from nexus.wallplan import plan_from_registry
    units = [
        {"name": "device.mtpx.1", "wall_model": "MTPX Plus 1616",
         "host": "10.0.0.15", "wall_slots": ["r1c1", "r1c2"], "wall_passes": 2},
        {"name": "device.mtpx.2", "wall_model": "MTPX Plus 128",
         "host": "10.0.0.16", "wall_slots": ["r2c1", "r2c2"], "wall_passes": 2},
    ]
    plan = plan_from_registry(units)
    assert [l.slot for l in plan.lanes] == ["r1c1", "r1c2", "r2c1", "r2c2"]
    # The 128's lanes only use skewable inputs 5-12.
    mtpx2 = [l for l in plan.lanes if l.unit == "device.mtpx.2"]
    assert all(all(i >= 5 for i in l.inputs) for l in mtpx2)
    # Matrix inputs number across the whole wall in slot order.
    assert [l.matrix_input for l in plan.lanes] == [1, 2, 3, 4]


def test_plan_from_registry_ignores_unslotted_units():
    from nexus.wallplan import plan_from_registry
    plan = plan_from_registry([
        {"name": "device.mtpx.1", "wall_model": "MTPX Plus 128",
         "wall_slots": ["r1c1"], "wall_passes": 2},
        {"name": "device.mtpx.spare", "wall_model": "MTPX Plus 128",
         "wall_slots": []},
    ])
    assert len(plan.lanes) == 1 and plan.lanes[0].unit == "device.mtpx.1"


def test_joe_wall_rack_artifacts():
    plan = joe_wall()
    # Identity matrix baseline: slot k in → out k, MGPs get 4 slots each.
    assert plan.matrix_ties()[0] == "1*1!"
    assert plan.matrix_ties()[15] == "16*16!"
    mgp = plan.mgp_assignment()
    assert mgp["r1c1"] == 1 and mgp["r1c4"] == 1
    assert mgp["r2c1"] == 2 and mgp["r4c4"] == 4
    # One loopback cable per 2-pass lane, 16 cables total.
    assert len(plan.patch_list()) == 16
    # Baseline unit ties: 2 per lane.
    ties = plan.unit_ties()
    assert len(ties["mtpx1"]) == 6 and len(ties["mtpx5"]) == 8
    # The ties-unverified warning always rides along.
    assert any("verified=false" in w for w in plan.warnings)
