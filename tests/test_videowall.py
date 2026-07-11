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
