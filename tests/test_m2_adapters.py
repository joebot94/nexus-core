"""M2 adapters: Matrix 12800, SMX, DMS 3600, generic extron_sis."""

import pytest

from nexus.adapters import ADAPTER_TYPES
from nexus.adapters.dms3600 import DMS3600Adapter
from nexus.adapters.extron_sis import ExtronSISAdapter
from nexus.adapters.matrix12800 import Matrix12800Adapter
from nexus.adapters.smx import SMXAdapter
from nexus.registry import DeviceConfig
from nexus.transports import SimTransport


def _sim(cls):
    config = DeviceConfig(device_id=f"device.{cls.device_type}.test", type=cls.device_type)
    return cls(config, SimTransport(cls.Simulator()))


def test_all_m2_types_registered():
    assert {"extron_sis", "matrix12800", "smx", "dms3600"} <= set(ADAPTER_TYPES)


@pytest.mark.asyncio
async def test_generic_extron_sis_universal_recall():
    adapter = _sim(ExtronSISAdapter)
    result = await adapter.execute("recall_preset", {"preset": 7})
    assert result.ok and result.response == "Rpr07"
    assert result.state == {"preset": 7}


@pytest.mark.asyncio
async def test_matrix_tie_untie_query():
    adapter = _sim(Matrix12800Adapter)
    tie = await adapter.execute("tie", {"input": 12, "output": 5})
    assert tie.ok and tie.state == {"output_5": 12}
    query = await adapter.execute("query_tie", {"output": 5})
    assert query.ok and query.state == {"output_5": 12} and query.state_source == "query"
    untie = await adapter.execute("untie", {"output": 5})
    assert untie.ok and untie.state == {"output_5": 0}


@pytest.mark.asyncio
async def test_smx_preset_is_rpr_not_universal_dot():
    """The whole reason the SMX has its own adapter: `N.` is rejected, RprNN works."""
    sim = SMXAdapter.Simulator()
    config = DeviceConfig(device_id="device.smx.test", type="smx")
    adapter = SMXAdapter(config, SimTransport(sim))
    result = await adapter.execute("recall_preset", {"preset": 3})
    assert result.ok and result.response == "Rpr03"
    assert result.state == {"preset": 3}
    # And the universal form really does fail on this device family.
    universal = await adapter.send("3.")
    assert not universal.ok and universal.error.startswith("E10")


@pytest.mark.asyncio
async def test_smx_plane_ties():
    adapter = _sim(SMXAdapter)
    video = await adapter.execute("tie", {"input": 4, "output": 2, "plane": "02"})
    assert video.ok and video.state == {"plane_02_output_2": 4}
    all_planes = await adapter.execute("tie_all_planes", {"input": 4, "output": 2})
    assert all_planes.ok
    assert all_planes.state == {f"plane_{p}_output_2": 4 for p in ("00", "01", "02", "04")}
    query = await adapter.execute("query_tie", {"output": 2, "plane": "04"})
    assert query.ok and query.state == {"plane_04_output_2": 4}
    from nexus.adapters.base import InvalidParams
    with pytest.raises(InvalidParams, match="one of"):
        await adapter.execute("tie", {"input": 1, "output": 1, "plane": "03"})


@pytest.mark.asyncio
async def test_dms_tie_and_recall():
    adapter = _sim(DMS3600Adapter)
    tie = await adapter.execute("tie", {"input": 36, "output": 36})
    assert tie.ok and tie.state == {"output_36": 36}
    recall = await adapter.execute("recall_preset", {"preset": 1})
    assert recall.ok and recall.state == {"preset": 1}


@pytest.mark.asyncio
async def test_profiles_constrain_each_installed_matrix():
    config = DeviceConfig(device_id="device.dms.small", type="dms3600",
                          hardware_profile={"inputs": 24, "outputs": 24})
    adapter = DMS3600Adapter(config, SimTransport(DMS3600Adapter.Simulator()))
    profile = adapter.hardware_profile()
    assert profile["inputs"] == 24 and profile["outputs"] == 24
    from nexus.adapters.base import InvalidParams
    with pytest.raises(InvalidParams, match="range 1-24"):
        await adapter.execute("tie", {"input": 25, "output": 1})
