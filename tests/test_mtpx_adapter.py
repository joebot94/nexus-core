"""MTPX Plus adapter — skew (the glitch technique), batch, peaking, presets."""

import pytest

from nexus.adapters import ADAPTER_TYPES
from nexus.adapters.base import InvalidParams
from nexus.adapters.mtpx import MTPXAdapter
from nexus.registry import DeviceConfig
from nexus.transports import SimTransport, TransportError


def _sim() -> MTPXAdapter:
    config = DeviceConfig(device_id="device.mtpx.test", type="mtpx")
    return MTPXAdapter(config, SimTransport(MTPXAdapter.Simulator()))


def test_mtpx_registered():
    assert ADAPTER_TYPES["mtpx"] is MTPXAdapter


@pytest.mark.asyncio
async def test_single_skew_builds_verified_wire_and_confirms():
    adapter = _sim()
    result = await adapter.execute("set_input_skew", {"input": 3, "r": 0, "g": 0, "b": 31})
    assert result.ok
    assert result.state == {"input_3_skew": [0, 0, 31]}
    # The sim echoes, so a matching echo confirms it.
    assert result.state_source == "command_ack"


@pytest.mark.asyncio
async def test_batch_skew_multiple_channels_one_call():
    adapter = _sim()
    result = await adapter.execute("set_input_skew_batch", {"channels": [
        {"input": 1, "r": 0, "g": 15, "b": 31},
        {"input": 2, "r": 31, "g": 0, "b": 0},
    ]})
    assert result.ok
    assert result.state == {"input_1_skew": [0, 15, 31], "input_2_skew": [31, 0, 0]}
    assert result.state_source == "command_ack"


@pytest.mark.asyncio
async def test_batch_validates_each_channel():
    adapter = _sim()
    with pytest.raises(InvalidParams, match="out of range"):
        await adapter.execute("set_input_skew_batch", {"channels": [{"input": 3, "r": 0, "g": 0, "b": 99}]})
    with pytest.raises(InvalidParams, match="integer input"):
        await adapter.execute("set_input_skew_batch", {"channels": [{"input": 3, "r": 0, "g": 0}]})
    with pytest.raises(InvalidParams, match="must not be empty"):
        await adapter.execute("set_input_skew_batch", {"channels": []})


@pytest.mark.asyncio
async def test_reset_skew_zeros_channel():
    adapter = _sim()
    result = await adapter.execute("reset_input_skew", {"input": 5})
    assert result.ok and result.state == {"input_5_skew": [0, 0, 0]}


@pytest.mark.asyncio
async def test_output_peaking():
    adapter = _sim()
    result = await adapter.execute("set_output_peaking", {"output": 2, "enabled": 1})
    assert result.ok and result.state == {"output_2_peaking": True}
    assert result.state_source == "command_ack"


@pytest.mark.asyncio
async def test_preset_recall_universal_form():
    adapter = _sim()
    result = await adapter.execute("recall_preset", {"preset": 3})
    assert result.ok and result.state == {"preset": 3}


@pytest.mark.asyncio
async def test_preset_save_is_comma_not_dot():
    """Save is `{N},` — the USP recall/save confusion in reverse. verified=False."""
    adapter = _sim()
    assert MTPXAdapter.actions["save_preset"].verified is False
    result = await adapter.execute("save_preset", {"preset": 7})
    assert result.ok
    assert result.state_source == "command_ack"   # sim echoes Spr07
    with pytest.raises(InvalidParams):
        await adapter.execute("save_preset", {"preset": 33})


@pytest.mark.asyncio
async def test_silent_device_still_succeeds_but_infers():
    """A no-response-mode MTPX (empty echo) is a SUCCESS, state marked inferred."""
    class SilentSim(MTPXAdapter.Simulator):
        def respond(self, command):
            return ""   # no-response mode: device stays silent
    config = DeviceConfig(device_id="device.mtpx.silent", type="mtpx")
    adapter = MTPXAdapter(config, SimTransport(SilentSim()))
    result = await adapter.execute("set_input_skew", {"input": 3, "r": 0, "g": 0, "b": 31})
    assert result.ok                          # write completed = success
    assert result.state == {"input_3_skew": [0, 0, 31]}
    assert result.state_source == "inferred"  # honest: sent, not confirmed


@pytest.mark.asyncio
async def test_offline_unit_reports_failure():
    """A powered-off unit (connect fails) must report ok=False, not a fake success."""
    class DeadTransport:
        async def exchange_batch(self, commands, terminator="\r\n", drain=0.3):
            raise TransportError("connect failed: timed out / unreachable")
    config = DeviceConfig(device_id="device.mtpx.off", type="mtpx")
    adapter = MTPXAdapter(config, DeadTransport())
    result = await adapter.execute("set_input_skew", {"input": 3, "r": 0, "g": 0, "b": 31})
    assert not result.ok and "connect failed" in result.error
    assert result.state == {}


@pytest.mark.asyncio
async def test_system_status_marked_unverified():
    adapter = _sim()
    caps = {a["action"]: a for a in adapter.capabilities()["actions"]}
    assert caps["query_system_status"]["verified"] is False
    assert caps["tie"]["verified"] is False
    assert caps["set_input_skew"]["verified"] is True
