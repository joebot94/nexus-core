"""Groups + scenes: the store (resolve/expand/persist) and the API endpoints
(fan-out, scene recall, dry-run) over simulated devices."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from nexus.app import create_app
from nexus.config import Settings
from nexus.scenes import Group, Scene, SceneStep, SceneStore


# ---- store -----------------------------------------------------------------

def test_store_bootstraps_defaults(tmp_path):
    store = SceneStore(tmp_path / "scenes.jbt")
    assert (tmp_path / "scenes.jbt").exists()
    assert "group.wall" in store.groups
    assert "scene.baseline" in store.scenes


def test_expand_flattens_group_steps(tmp_path):
    store = SceneStore(tmp_path / "scenes.jbt")
    store.groups["group.two"] = Group(id="group.two", targets=["device.a", "device.b"])
    scene = Scene(id="s", steps=[
        SceneStep(target="group.two", action="recall_preset", parameters={"preset": 1}),
        SceneStep(target="device.c", action="recall_preset", parameters={"preset": 2}),
    ])
    expanded = store.expand(scene)
    assert [s.target for s in expanded] == ["device.a", "device.b", "device.c"]
    # Group members inherit the step's action + a COPY of its parameters.
    assert expanded[0].parameters == {"preset": 1} and expanded[1].parameters == {"preset": 1}


def test_unresolved_targets_flags_unknowns(tmp_path):
    store = SceneStore(tmp_path / "scenes.jbt")
    scene = Scene(id="s", steps=[SceneStep(target="device.ghost", action="x")])
    assert store.unresolved_targets(scene, {"device.real"}) == ["device.ghost"]
    assert store.unresolved_targets(scene, {"device.ghost"}) == []


def test_upsert_persists_and_reloads(tmp_path):
    path = tmp_path / "scenes.jbt"
    store = SceneStore(path)
    store.upsert_scene(Scene(id="scene.custom", label="Mine",
                             steps=[SceneStep(target="device.mgp.1", action="recall_preset",
                                              parameters={"preset": 60})]))
    reloaded = SceneStore(path)
    assert "scene.custom" in reloaded.scenes
    assert reloaded.scenes["scene.custom"].steps[0].parameters == {"preset": 60}


def test_malformed_entries_skip_with_warning(tmp_path):
    import json
    path = tmp_path / "scenes.jbt"
    SceneStore(path)  # bootstrap
    doc = json.loads(path.read_text())
    doc["payload"]["groups"].append({"label": "no id"})   # missing required id
    path.write_text(json.dumps(doc))
    store = SceneStore(path)
    assert any("skipped malformed group" in w for w in store.load_warnings)
    assert "group.wall" in store.groups     # the good ones still load


# ---- API -------------------------------------------------------------------

@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEXUS_SIMULATE", "1")
    app = create_app(Settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_groups_and_scenes_list(client):
    g = await client.get("/api/v1/groups")
    assert g.status_code == 200
    assert any(x["id"] == "group.wall" for x in g.json())
    s = await client.get("/api/v1/scenes")
    assert any(x["id"] == "scene.baseline" for x in s.json())


@pytest.mark.asyncio
async def test_group_fan_out_hits_every_member(client):
    # group.mgps default = [device.mgp.1]; add the sim so we can fire safely.
    await client.post("/api/v1/scenes/reload")  # ensure defaults loaded
    r = await client.post("/api/v1/groups/group.mgps/actions",
                          json={"action": "recall_preset", "parameters": {"preset": 50}})
    assert r.status_code == 200
    body = r.json()
    assert body["group"] == "group.mgps"
    assert [res["target"] for res in body["results"]] == ["device.mgp.1"]


@pytest.mark.asyncio
async def test_group_unknown_404(client):
    r = await client.post("/api/v1/groups/group.nope/actions",
                          json={"action": "recall_preset", "parameters": {"preset": 1}})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_scene_dry_run_does_not_fire(client):
    r = await client.post("/api/v1/scenes/scene.baseline/recall?dry_run=true")
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["steps"][0]["target"] == "device.mgp.1"
    assert body["steps"][0]["known_device"] is True
    # State must be untouched by a dry run.
    st = await client.get("/api/v1/devices/device.mgp.1/state")
    assert "preset" not in st.json()["state"]


@pytest.mark.asyncio
async def test_scene_recall_fires_steps_and_updates_state(client):
    r = await client.post("/api/v1/scenes/scene.baseline/recall")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["scene"] == "scene.baseline"
    assert body["results"][0]["state"] == {"preset": 48}
    st = await client.get("/api/v1/devices/device.mgp.1/state")
    assert st.json()["state"]["preset"]["value"] == 48


@pytest.mark.asyncio
async def test_scene_recall_unknown_404(client):
    r = await client.post("/api/v1/scenes/scene.ghost/recall")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_wall_plan_from_registry_metadata(client):
    r = await client.get("/api/v1/wall/plan")
    assert r.status_code == 200
    body = r.json()
    # Default registry ships example placement on the two MTPX units.
    assert body["configured"] is True
    slots = [l["slot"] for l in body["lanes"]]
    assert slots == ["r1c1", "r1c2", "r2c1", "r2c2"]
    assert body["matrix_ties"][0] == "1*1!"
    assert body["mgp_assignment"]["r1c1"] == 1
    # One loopback cable per 2-pass lane.
    assert len(body["patch_list"]) == 4


@pytest.mark.asyncio
async def test_generate_wall_baseline_scene(client):
    r = await client.post("/api/v1/wall/baseline-scene")
    assert r.status_code == 200
    scene = r.json()["scene"]
    assert scene["id"] == "scene.wall-baseline"
    actions = {s["action"] for s in scene["steps"]}
    assert {"tie", "reset_input_skew", "recall_preset"} <= actions
    # It's now listable and dry-runnable.
    listed = await client.get("/api/v1/scenes")
    assert any(s["id"] == "scene.wall-baseline" for s in listed.json())
    dry = await client.post("/api/v1/scenes/scene.wall-baseline/recall?dry_run=true")
    assert dry.json()["dry_run"] is True and len(dry.json()["steps"]) == len(scene["steps"])


def test_build_wall_baseline_from_plan():
    from nexus.scenes import build_wall_baseline_scene
    from nexus.wallplan import plan_from_registry
    plan = plan_from_registry([
        {"name": "device.mtpx.1", "wall_model": "MTPX Plus 128",
         "wall_slots": ["r1c1"], "wall_passes": 2}])
    scene = build_wall_baseline_scene(plan)
    # 2 ties + 2 skew-0 for the one 2-pass lane, + 1 matrix tie + 1 MGP preset.
    kinds = [s.action for s in scene.steps]
    assert kinds.count("tie") == 3 and kinds.count("reset_input_skew") == 2
    assert kinds[-1] == "recall_preset"
