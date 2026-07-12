"""MGP video-wall composition layer — topology, tile→builder resolution, the
DMS-hub signal path, and move-mechanism reach/rate."""

import pytest

from nexus.videowall import (
    DMSPorts, Mechanism, Orientation, Signal, Tile, VideowallError, WallConfig,
    cells, clamp_rate, max_rate_hz, mechanisms_for_move, resolve_builder,
    tile_path, LAYOUTS,
)


def _wall_3x3(signal=Signal.DIGITAL) -> WallConfig:
    return WallConfig(
        tiles=9, orientation=Orientation.HORIZONTAL, signal=signal,
        builder_devices=["device.mgp.1", "device.mgp.2", "device.mgp.3"],
        combiner_device="device.mgp.5",
        source_device="device.ipcp.wallctl",
        mtpx_devices=["device.mtpx.1", "device.mtpx.2", "device.mtpx.3"])


# ---- topology --------------------------------------------------------------

def test_layout_table_matches_glitchwall():
    assert LAYOUTS[4].rows == 2 and LAYOUTS[4].builders_used == 2
    assert LAYOUTS[9].rows == 3 and LAYOUTS[9].builders_used == 3
    assert LAYOUTS[16].rows == 4 and LAYOUTS[16].builders_used == 4


def test_resolve_builder_horizontal_owns_rows():
    spec = LAYOUTS[9]
    # top row (row 0) → builder 0, windows 1..3 across the columns
    assert resolve_builder(Tile(0, 0), Orientation.HORIZONTAL) == (0, 1)
    assert resolve_builder(Tile(0, 2), Orientation.HORIZONTAL) == (0, 3)
    # bottom-left (row 2, col 0) → builder 2, window 1
    assert resolve_builder(Tile(2, 0), Orientation.HORIZONTAL) == (2, 1)
    assert len(cells(spec)) == 9


def test_resolve_builder_vertical_owns_columns():
    assert resolve_builder(Tile(0, 0), Orientation.VERTICAL) == (0, 1)
    assert resolve_builder(Tile(2, 1), Orientation.VERTICAL) == (1, 3)


def test_single_mgp_for_2x2():
    assert WallConfig(tiles=4).is_single_mgp
    assert not WallConfig(tiles=9).is_single_mgp


def test_unknown_layout_raises():
    with pytest.raises(VideowallError):
        WallConfig(tiles=7).layout


# ---- signal path -----------------------------------------------------------

def test_digital_3x3_path_hubs_through_dms_three_times():
    wall = _wall_3x3()
    # top-left tile (0,0): tile index 0 → builder mgp.1 window 1
    hops = tile_path(Tile(0, 0), wall)
    joined = " | ".join(f"{h.stage}:{h.device}:{h.detail}" for h in hops)
    assert "DMS in 1" in joined and "device.mgp.1 DVI in 1" in joined   # stage 1
    assert "DMS in 17" in joined                                        # builder→combiner
    assert "device.mgp.5" in joined                                     # combiner
    assert "DMS out 22 → wall" in joined                               # final output
    # DMS appears as the fabric across multiple hops.
    assert sum(1 for h in hops if h.device == "device.dms.main") >= 3


def test_bottom_row_tile_uses_third_builder_and_return_19():
    wall = _wall_3x3()
    hops = tile_path(Tile(2, 1), wall)     # bottom row, middle col → builder 2
    joined = " | ".join(h.detail for h in hops)
    assert "device.mgp.3" in " ".join(h.device for h in hops)
    assert "DMS in 19" in joined           # builder_return_base 17 + builder 2
    assert "in 3" in joined                # combiner input for builder index 2 → 3


def test_rgb_path_has_skew_stage_only():
    wall = _wall_3x3(signal=Signal.RGB)
    hops = tile_path(Tile(0, 0), wall)
    stages = [h.stage for h in hops]
    assert "skew" in stages
    skew = next(h for h in hops if h.stage == "skew")
    assert "62ns" in skew.detail and skew.device == "device.mtpx.1"
    # Digital path has NO skew stage.
    assert "skew" not in [h.stage for h in tile_path(Tile(0, 0), _wall_3x3())]


def test_composite_path_routes_through_12800():
    wall = _wall_3x3(signal=Signal.COMPOSITE)
    hops = tile_path(Tile(0, 0), wall)
    joined = " | ".join(f"{h.device}:{h.detail}" for h in hops)
    assert "composite adapter" in joined
    assert "device.matrix.main" in joined and "12800" in joined
    assert "skew" not in [h.stage for h in hops]


def test_2x2_single_mgp_assembles_inline():
    wall = WallConfig(tiles=4, builder_devices=["device.mgp.1"],
                      combiner_device="device.mgp.1", source_device="src")
    hops = tile_path(Tile(0, 0), wall)
    # No DMS return trip — the same MGP builds and combines.
    assert not any("DMS in 17" in h.detail for h in hops)
    assert any(h.stage == "assemble" and "same MGP" in h.detail for h in hops)


# ---- move mechanisms -------------------------------------------------------

def test_same_square_is_input_remap():
    wall = _wall_3x3()
    assert mechanisms_for_move(Tile(0, 0), Tile(0, 0), wall) == [Mechanism.INPUT_REMAP]


def test_same_mgp_different_square_needs_window_move():
    wall = _wall_3x3()
    # (0,0) and (0,2) are both row 0 → same builder, different position.
    assert mechanisms_for_move(Tile(0, 0), Tile(0, 2), wall) == [Mechanism.WINDOW_MOVE]


def test_cross_mgp_needs_routing():
    wall = _wall_3x3()
    # top-left → bottom-right = different builders → routing (Joe's tile 1 → 16).
    moves = mechanisms_for_move(Tile(0, 0), Tile(2, 2), wall)
    assert Mechanism.DVI_CROSSPOINT in moves
    # On an analog wall, analog route is offered first (no handshake).
    rgb_moves = mechanisms_for_move(Tile(0, 0), Tile(2, 2), _wall_3x3(Signal.RGB))
    assert rgb_moves[0] == Mechanism.ANALOG_ROUTE


def test_rate_ceilings_clamp():
    assert max_rate_hz(Mechanism.INPUT_REMAP) == 15.0
    assert clamp_rate(15.0, Mechanism.WINDOW_MOVE) == 4.0   # window move caps low
    assert clamp_rate(2.0, Mechanism.INPUT_REMAP) == 2.0    # under ceiling: unchanged


# ---- API -------------------------------------------------------------------

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from nexus.app import create_app
from nexus.config import Settings


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEXUS_SIMULATE", "1")
    app = create_app(Settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_videowall_plan_endpoint_resolves_all_tiles(client):
    r = await client.post("/api/v1/wall/videowall/plan", json={
        "tiles": 9, "signal": "digital",
        "builder_devices": ["device.mgp.1", "device.mgp.2", "device.mgp.3"],
        "combiner_device": "device.mgp.5", "source_device": "wallctl"})
    assert r.status_code == 200
    body = r.json()
    assert body["grid"] == "3×3" and len(body["resolved"]) == 9
    assert body["single_mgp"] is False
    first = body["resolved"][0]
    assert first["builder_index"] == 0 and first["window"] == 1
    assert any("DMS out 22 → wall" in h["detail"] for h in first["path"])


@pytest.mark.asyncio
async def test_videowall_plan_rejects_bad_grid(client):
    r = await client.post("/api/v1/wall/videowall/plan", json={"tiles": 7})
    assert r.status_code == 422


# ---- baseline scene generation ---------------------------------------------

def test_baseline_steps_shape():
    from nexus.videowall import baseline_steps
    steps = baseline_steps(_wall_3x3())
    actions = [s["action"] for s in steps]
    assert actions[0] == "set_wall_mode"                 # source grid mode first
    assert actions.count("recall_preset") == 4           # 3 builders + 1 combiner
    assert actions.count("tie") == 9 + 3 + 1             # source(9) + returns(3) + out(1)


def test_single_mgp_baseline_is_compact():
    from nexus.videowall import WallConfig, baseline_steps
    wall = WallConfig(tiles=4, builder_devices=["device.mgp.1"],
                      combiner_device="device.mgp.1", source_device="src")
    actions = [s["action"] for s in baseline_steps(wall)]
    assert actions.count("recall_preset") == 1           # one MGP does all
    assert actions.count("tie") == 4                     # 4 source ties, no return trip


@pytest.mark.asyncio
async def test_videowall_baseline_scene_generated_and_saved(client):
    r = await client.post("/api/v1/wall/videowall/baseline-scene", json={
        "tiles": 9, "signal": "digital",
        "builder_devices": ["device.mgp.1", "device.mgp.2", "device.mgp.3"],
        "combiner_device": "device.mgp.5", "source_device": "wallctl",
        "dms_device": "device.dms.main"})
    assert r.status_code == 200
    assert r.json()["scene"]["id"] == "scene.videowall-baseline"
    listed = await client.get("/api/v1/scenes")
    assert any(s["id"] == "scene.videowall-baseline" for s in listed.json())


@pytest.mark.asyncio
async def test_videowall_baseline_recall_is_resilient(client):
    """The IR source-mode step isn't wired yet, so it must fail GRACEFULLY —
    the recall completes and records it, never aborts the whole scene."""
    await client.post("/api/v1/wall/videowall/baseline-scene", json={
        "tiles": 9, "builder_devices": ["device.mgp.1"],
        "combiner_device": "device.mgp.1", "source_device": "wallctl",
        "dms_device": "device.dms.main"})
    r = await client.post("/api/v1/scenes/scene.videowall-baseline/recall")
    assert r.status_code == 200                          # NOT aborted by the unsupported step
    results = r.json()["results"]
    assert results[0]["action"] == "set_wall_mode" and results[0]["ok"] is False
    assert any(x["ok"] for x in results)                 # real steps still fired


# ---- scramble generator ----------------------------------------------------

def test_scramble_is_a_derangement():
    from nexus.videowall import scramble_steps
    wall = _wall_3x3()   # horizontal → each builder = 1×3 row = 3 windows
    steps = scramble_steps(wall, builders=[0], seed=0)
    # Every window on builder 0 gets a DIFFERENT input than its own number.
    assert len(steps) == 3
    for s in steps:
        assert s["parameters"]["input"] != s["parameters"]["window"]   # no fixed point
        assert s["action"] == "route_input_to_window"
    inputs = sorted(s["parameters"]["input"] for s in steps)
    assert inputs == [1, 2, 3]                       # a true permutation


def test_scramble_per_region_selection():
    from nexus.videowall import scramble_steps
    wall = _wall_3x3()
    only_top = scramble_steps(wall, builders=[0], seed=1)
    assert {s["target"] for s in only_top} == {"device.mgp.1"}   # just that quadrant
    whole = scramble_steps(wall, seed=1)
    assert {s["target"] for s in whole} == {"device.mgp.1", "device.mgp.2", "device.mgp.3"}


def test_scramble_deterministic_from_seed():
    from nexus.videowall import scramble_steps
    wall = _wall_3x3()
    assert scramble_steps(wall, seed=5) == scramble_steps(wall, seed=5)


@pytest.mark.asyncio
async def test_scramble_scene_endpoint(client):
    r = await client.post("/api/v1/wall/videowall/scramble-scene", json={
        "tiles": 9, "builders": [0], "seed": 3,
        "builder_devices": ["device.mgp.1", "device.mgp.2", "device.mgp.3"],
        "combiner_device": "device.mgp.5"})
    assert r.status_code == 200
    scene = r.json()["scene"]
    assert scene["id"] == "scene.videowall-scramble"
    assert all(s["action"] == "route_input_to_window" for s in scene["steps"])


# ---- skew burst generator --------------------------------------------------

def test_skew_burst_rgb_only():
    from nexus.videowall import skew_burst_steps
    assert skew_burst_steps(_wall_3x3(Signal.DIGITAL), r=0, g=0, b=31) == []
    assert skew_burst_steps(_wall_3x3(Signal.COMPOSITE), r=0, g=0, b=31) == []
    rgb = skew_burst_steps(_wall_3x3(Signal.RGB), r=0, g=0, b=31)
    assert rgb                                        # RGB wall produces steps


def test_skew_burst_groups_by_mtpx_and_targets_right_input():
    from nexus.videowall import Tile, skew_burst_steps
    wall = _wall_3x3(Signal.RGB)
    # skew just the top row (tiles (0,0),(0,1),(0,2)) → all on mtpx.1, inputs 1-3
    steps = skew_burst_steps(wall, tiles=[Tile(0, 0), Tile(0, 1), Tile(0, 2)], b=20)
    assert len(steps) == 1 and steps[0]["target"] == "device.mtpx.1"
    assert steps[0]["action"] == "set_input_skew_batch"
    inputs = sorted(c["input"] for c in steps[0]["parameters"]["channels"])
    assert inputs == [1, 2, 3]
    assert all(c["b"] == 20 for c in steps[0]["parameters"]["channels"])


def test_skew_burst_random_is_deterministic_and_bounded():
    from nexus.videowall import skew_burst_steps
    wall = _wall_3x3(Signal.RGB)
    a = skew_burst_steps(wall, random_seed=7, max_skew=31)
    b = skew_burst_steps(wall, random_seed=7, max_skew=31)
    assert a == b                                     # deterministic
    vals = [v for s in a for c in s["parameters"]["channels"] for v in (c["r"], c["g"], c["b"])]
    assert all(0 <= v <= 31 for v in vals)


@pytest.mark.asyncio
async def test_skew_scene_endpoint_rejects_digital(client):
    r = await client.post("/api/v1/wall/videowall/skew-scene", json={
        "tiles": 9, "signal": "digital", "b": 31,
        "mtpx_devices": ["device.mtpx.1", "device.mtpx.2", "device.mtpx.3"]})
    assert r.status_code == 422                        # skew is RGB-only


@pytest.mark.asyncio
async def test_skew_scene_endpoint_rgb(client):
    r = await client.post("/api/v1/wall/videowall/skew-scene", json={
        "tiles": 9, "signal": "rgb", "random": True, "seed": 4,
        "mtpx_devices": ["device.mtpx.1", "device.mtpx.2", "device.mtpx.3"]})
    assert r.status_code == 200
    scene = r.json()["scene"]
    assert scene["id"] == "scene.videowall-skew"
    assert all(s["action"] == "set_input_skew_batch" for s in scene["steps"])


# ---- freeze / blank generator ----------------------------------------------

def test_freeze_steps_target_builder_windows():
    from nexus.videowall import Tile, freeze_steps
    wall = _wall_3x3()
    steps = freeze_steps(wall, tiles=[Tile(1, 2)], mode="freeze")   # mid row, col 3
    assert len(steps) == 1
    assert steps[0]["target"] == "device.mgp.2" and steps[0]["action"] == "set_window_freeze"
    assert steps[0]["parameters"] == {"window": 3, "on": 1}


def test_blank_mode_and_release():
    from nexus.videowall import freeze_steps
    wall = _wall_3x3()
    blanked = freeze_steps(wall, mode="blank", on=False)
    assert all(s["action"] == "set_window_blank" and s["parameters"]["on"] == 0 for s in blanked)


def test_bad_mode_raises():
    from nexus.videowall import VideowallError, freeze_steps
    with pytest.raises(VideowallError):
        freeze_steps(_wall_3x3(), mode="explode")


@pytest.mark.asyncio
async def test_freeze_scene_endpoint_fires_on_sim(client):
    r = await client.post("/api/v1/wall/videowall/freeze-scene", json={
        "tiles": 4, "mode": "freeze",
        "builder_devices": ["device.mgp.1"], "combiner_device": "device.mgp.1"})
    assert r.status_code == 200
    scene = r.json()["scene"]
    assert scene["id"] == "scene.videowall-freeze"
    # And it actually fires on the MGP sim (the new blank/freeze action).
    recall = await client.post("/api/v1/scenes/scene.videowall-freeze/recall")
    assert recall.status_code == 200
    assert any(x["ok"] for x in recall.json()["results"])


@pytest.mark.asyncio
async def test_mgp_freeze_action_on_sim(client):
    r = await client.post("/api/v1/actions", json={
        "target": "device.mgp.sim", "action": "set_window_freeze",
        "parameters": {"window": 2, "on": 1}})
    assert r.status_code == 200
    assert r.json()["ok"] and r.json()["state"] == {"window_2_freeze": True}


# ---- composed chaos generator ----------------------------------------------

def test_chaos_one_region_crazy_rest_clean():
    from nexus.videowall import RegionChaos, chaos_steps
    wall = _wall_3x3(Signal.RGB)
    # Only builder 0 goes wild (scramble + skew + freeze); 1 and 2 untouched.
    steps = chaos_steps(wall, [RegionChaos(builder=0, scramble=True, skew=31, freeze=True)], seed=2)
    devices = {s["target"] for s in steps}
    assert "device.mgp.1" in devices and "device.mtpx.1" in devices   # scramble+freeze, skew
    assert "device.mgp.2" not in devices and "device.mgp.3" not in devices   # rest clean
    actions = {s["action"] for s in steps}
    assert actions == {"route_input_to_window", "set_input_skew_batch", "set_window_freeze"}


def test_chaos_skew_dropped_on_digital():
    from nexus.videowall import RegionChaos, chaos_steps
    wall = _wall_3x3(Signal.DIGITAL)
    steps = chaos_steps(wall, [RegionChaos(builder=0, scramble=True, skew=31)], seed=1)
    assert not any(s["action"] == "set_input_skew_batch" for s in steps)   # no skew on digital
    assert any(s["action"] == "route_input_to_window" for s in steps)      # scramble still applies


@pytest.mark.asyncio
async def test_chaos_scene_endpoint(client):
    r = await client.post("/api/v1/wall/videowall/chaos-scene", json={
        "tiles": 9, "signal": "rgb", "seed": 5,
        "builder_devices": ["device.mgp.1", "device.mgp.2", "device.mgp.3"],
        "combiner_device": "device.mgp.5",
        "mtpx_devices": ["device.mtpx.1", "device.mtpx.2", "device.mtpx.3"],
        "regions": [{"builder": 0, "scramble": True, "skew": 20, "freeze": True}]})
    assert r.status_code == 200
    assert r.json()["scene"]["id"] == "scene.videowall-chaos"


@pytest.mark.asyncio
async def test_chaos_scene_needs_a_region(client):
    r = await client.post("/api/v1/wall/videowall/chaos-scene", json={"tiles": 9})
    assert r.status_code == 422
