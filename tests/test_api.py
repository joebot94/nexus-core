import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from nexus.app import create_app
from nexus.config import Settings


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEXUS_SIMULATE", "1")   # every device simulated in tests
    app = create_app(Settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["service"] == "nexus-core"


@pytest.mark.asyncio
async def test_devices_bootstrap_registry(client, tmp_path):
    r = await client.get("/api/v1/devices")
    assert r.status_code == 200
    ids = [d["device_id"] for d in r.json()]
    assert "device.mgp.1" in ids and "device.mgp.sim" in ids
    assert (tmp_path / "jbt" / "device_registry.jbt").exists()


@pytest.mark.asyncio
async def test_action_roundtrip_updates_state_and_events(client):
    r = await client.post("/api/v1/actions", json={
        "target": "device.mgp.sim", "action": "recall_preset",
        "parameters": {"preset": 51}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["state"] == {"preset": 51}
    assert body["response"] == "Rpr2*051"

    r = await client.get("/api/v1/devices/device.mgp.sim/state")
    state = r.json()["state"]
    assert state["preset"]["value"] == 51
    assert state["preset"]["source"] == "command_ack"

    r = await client.get("/api/v1/events")
    assert any("recall_preset preset=51" in e["summary"] for e in r.json())


@pytest.mark.asyncio
async def test_action_validation_errors(client):
    r = await client.post("/api/v1/actions", json={
        "target": "device.mgp.sim", "action": "recall_preset", "parameters": {}})
    assert r.status_code == 422
    r = await client.post("/api/v1/actions", json={
        "target": "device.mgp.sim", "action": "nope", "parameters": {}})
    assert r.status_code == 400
    r = await client.post("/api/v1/actions", json={
        "target": "device.nope", "action": "recall_preset", "parameters": {"preset": 1}})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_probe_and_capabilities(client):
    r = await client.post("/api/v1/devices/device.mgp.sim/probe")
    assert r.json()["ok"] and r.json()["state"]["model"] == "MGP 464 DI"
    r = await client.get("/api/v1/devices/device.mgp.sim/capabilities")
    actions = {a["action"] for a in r.json()["actions"]}
    assert {"recall_preset", "route_input_to_window", "query_window"} <= actions


@pytest.mark.asyncio
async def test_hardware_profile_is_exposed_without_sending_commands(client):
    r = await client.get("/api/v1/devices/device.dms.main/hardware-profile")
    assert r.status_code == 200
    body = r.json()
    assert body["profile"]["kind"] == "matrix"
    assert body["profile"]["inputs"] == body["profile"]["outputs"] == 36
    assert body["profile"]["source"] == "configured"


@pytest.mark.asyncio
async def test_raw_endpoint_is_guarded(client):
    r = await client.post("/api/v1/devices/device.mgp.sim/raw",
                          json={"command": "Q"})
    assert r.status_code == 400 and "confirm_raw" in r.json()["detail"]
    r = await client.post("/api/v1/devices/device.mgp.sim/raw",
                          json={"command": "Q", "confirm_raw": True})
    assert r.status_code == 200 and r.json()["response"] == "1.12"


@pytest.mark.asyncio
async def test_registry_reload_picks_up_new_device(client, tmp_path):
    import json
    path = tmp_path / "jbt" / "device_registry.jbt"
    doc = json.loads(path.read_text())
    doc["payload"]["devices"].append({
        "device_id": "device.new.1", "type": "extron_sis",
        "label": "Fresh Box", "host": "sim", "simulate": True})
    doc["payload"]["devices"].append({
        "device_id": "device.broken.1", "type": "flux_capacitor"})
    path.write_text(json.dumps(doc))

    r = await client.post("/api/v1/registry/reload")
    body = r.json()
    assert body["ok"]
    assert len(body["warnings"]) == 1 and "flux_capacitor" in body["warnings"][0]
    r = await client.post("/api/v1/actions", json={
        "target": "device.new.1", "action": "recall_preset", "parameters": {"preset": 5}})
    assert r.json()["ok"] and r.json()["state"] == {"preset": 5}


@pytest.mark.asyncio
async def test_token_auth_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NEXUS_SIMULATE", "1")
    monkeypatch.setenv("NEXUS_TOKEN", "jenny8675")
    app = create_app(Settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/v1/devices")).status_code == 401
        r = await c.get("/api/v1/devices", headers={"X-Nexus-Token": "jenny8675"})
        assert r.status_code == 200
        r = await c.get("/api/v1/devices", headers={"Authorization": "Bearer jenny8675"})
        assert r.status_code == 200
        # health stays open for Docker healthchecks
        assert (await c.get("/api/v1/health")).status_code == 200
