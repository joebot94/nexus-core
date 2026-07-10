import pytest

from nexus.adapters.base import InvalidParams, UnsupportedAction
from nexus.adapters.extron_sis import ExtronSISAdapter
from nexus.adapters.mgp import MGP464Adapter
from nexus.registry import DeviceConfig
from nexus.transports import SimTransport, TCPTransport


def _sim_adapter() -> MGP464Adapter:
    config = DeviceConfig(device_id="device.mgp.test", type="mgp464", host="sim")
    return MGP464Adapter(config, SimTransport(MGP464Adapter.Simulator()))


@pytest.mark.asyncio
async def test_recall_preset_builds_mgp_wire_and_parses_ack():
    adapter = _sim_adapter()
    result = await adapter.execute("recall_preset", {"preset": 48})
    assert result.ok
    assert result.response == "Rpr2*048"     # the verified zero-padded ack
    assert result.state == {"preset": 48}    # state confirmed from the ack, not the send


@pytest.mark.asyncio
async def test_window_route_and_query():
    adapter = _sim_adapter()
    route = await adapter.execute("route_input_to_window", {"input": 3, "window": 1})
    assert route.ok and route.state == {"window_1": 3}
    query = await adapter.execute("query_window", {"window": 1})
    assert query.ok and query.state == {"window_1": 3}
    assert query.state_source == "query"       # reads are stamped as queries
    assert route.state_source == "command_ack"  # sets are stamped as acks


@pytest.mark.asyncio
async def test_param_validation():
    adapter = _sim_adapter()
    with pytest.raises(InvalidParams, match="range 1-128"):
        await adapter.execute("recall_preset", {"preset": 999})
    with pytest.raises(InvalidParams, match="missing required"):
        await adapter.execute("recall_preset", {})
    with pytest.raises(InvalidParams, match="unknown parameter"):
        await adapter.execute("recall_preset", {"preset": 48, "bogus": 1})
    with pytest.raises(UnsupportedAction):
        await adapter.execute("do_a_backflip", {})


@pytest.mark.asyncio
async def test_sis_error_normalized():
    adapter = _sim_adapter()
    result = await adapter.send("NOPE")
    assert not result.ok
    assert result.error == "E10: invalid command"


@pytest.mark.asyncio
async def test_probe_parses_model_from_banner(fake_sis_server):
    host, port, _sim = fake_sis_server
    config = DeviceConfig(device_id="device.mgp.tcp", type="mgp464", host=host, port=port)
    adapter = MGP464Adapter(config, TCPTransport(host, port, banner_window=0.15))
    result = await adapter.probe()
    assert result.ok
    assert result.state["model"] == "MGP 464 DI"
    assert result.state["firmware"] == "1.12"


@pytest.mark.asyncio
async def test_recall_preset_over_real_tcp(fake_sis_server):
    """The full vertical-slice wire path: adapter → TCP → SIS device → ack."""
    host, port, sim = fake_sis_server
    config = DeviceConfig(device_id="device.mgp.tcp", type="mgp464", host=host, port=port)
    adapter = MGP464Adapter(config, TCPTransport(host, port, banner_window=0.15))
    result = await adapter.execute("recall_preset", {"preset": 52})
    assert result.ok and result.state == {"preset": 52}
    assert sim.preset == 52


def test_universal_extron_recall_differs_from_mgp():
    # Family base sends `N.`; the MGP override must send `2*N.` — the whole
    # point of the adapter hierarchy.
    assert "recall_preset" in ExtronSISAdapter.actions
    assert "recall_preset" in MGP464Adapter.actions
    assert MGP464Adapter.do_recall_preset is not ExtronSISAdapter.do_recall_preset
