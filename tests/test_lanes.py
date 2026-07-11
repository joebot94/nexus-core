"""LanePoolTransport — N concurrent sockets, burst fanned across lanes,
fire-and-forget best-effort semantics. Ported from Joe's MTPXControl approach.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from nexus.adapters.mtpx import MTPXAdapter
from nexus.registry import DeviceConfig
from nexus.transports import LanePoolTransport, TransportError


class MTPXLaneSim:
    """Fake MTPX on a real TCP server that accepts many connections and records
    which connection each command arrived on (to prove parallel fan-out)."""

    def __init__(self, *, silent: bool = False) -> None:
        self.silent = silent
        self.connections = 0
        self.peak_concurrent = 0
        self._active = 0
        self.commands: list[str] = []
        self.per_conn: list[int] = []          # commands seen per connection
        self.host = ""
        self.port = 0
        self._server: asyncio.Server | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.host, self.port = self._server.sockets[0].getsockname()[:2]

    async def stop(self) -> None:
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, reader, writer):
        conn_index = self.connections
        self.connections += 1
        self.per_conn.append(0)
        self._active += 1
        self.peak_concurrent = max(self.peak_concurrent, self._active)
        writer.write(b"(c) Copyright 2024, Extron Electronics, MTPX Plus 1616, V1.04\r\n")
        await writer.drain()
        try:
            while True:
                data = await reader.readuntil(b"\r\n")
                cmd = data.decode(errors="replace").strip()
                if not cmd:
                    continue
                async with self._lock:
                    self.commands.append(cmd)
                    self.per_conn[conn_index] += 1
                if not self.silent:
                    # Echo an Iseq ack so the confirmation path can be exercised.
                    import re
                    if m := re.fullmatch(r"W(\d+)\*(\d+)\*(\d+)\*(\d+)Iseq", cmd):
                        i, r, g, b = (int(x) for x in m.groups())
                        writer.write(f"Iseq{i:02d} {r:02d} {g:02d} {b:02d}\r\n".encode())
                        await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            self._active -= 1
            writer.close()


@pytest_asyncio.fixture
async def mtpx():
    sim = MTPXLaneSim()
    await sim.start()
    yield sim
    await sim.stop()


@pytest.mark.asyncio
async def test_opens_requested_lane_count(mtpx):
    pool = LanePoolTransport(mtpx.host, mtpx.port, lane_count=10, banner_window=0.05)
    try:
        await pool.exchange_batch([f"W{i}*0*0*31Iseq" for i in range(5, 13)],
                                  drain=0.1)
        assert pool.stats["lane_opens"] == 10
        assert mtpx.peak_concurrent == 10       # all lanes open at once
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_burst_is_fanned_across_lanes(mtpx):
    pool = LanePoolTransport(mtpx.host, mtpx.port, lane_count=4, banner_window=0.05)
    try:
        cmds = [f"W{i}*0*0*31Iseq" for i in range(5, 13)]   # 8 commands, 4 lanes
        await pool.exchange_batch(cmds, drain=0.15)
        await asyncio.sleep(0.05)
        assert sorted(mtpx.commands) == sorted(cmds)         # all delivered
        # 8 commands across 4 lanes → 2 each (round-robin), not all on one.
        assert max(mtpx.per_conn) <= 3
        assert sum(1 for c in mtpx.per_conn if c > 0) == 4   # every lane used
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_silent_device_burst_still_succeeds(mtpx):
    """MTPX no-response mode: writes complete, no echo — still a success."""
    mtpx.silent = True
    pool = LanePoolTransport(mtpx.host, mtpx.port, lane_count=4, banner_window=0.05)
    try:
        reply = await pool.exchange_batch(["W5*0*0*31Iseq", "W6*0*0*31Iseq"], drain=0.1)
        assert reply.response == ""                          # silence
        await asyncio.sleep(0.05)
        assert len(mtpx.commands) == 2                       # but delivered
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_offline_device_raises(mtpx):
    pool = LanePoolTransport("127.0.0.1", 1, lane_count=4, connect_timeout=0.3)
    with pytest.raises(TransportError):
        await pool.exchange_batch(["W5*0*0*31Iseq"], drain=0.1)
    await pool.aclose()


@pytest.mark.asyncio
async def test_mtpx_adapter_skew_batch_over_lanes(mtpx):
    """End-to-end: the MTPX adapter's set_input_skew_batch fans across lanes
    with no adapter change (exchange_batch is transport-swappable)."""
    config = DeviceConfig(device_id="device.mtpx.lanes", type="mtpx")
    pool = LanePoolTransport(mtpx.host, mtpx.port, lane_count=8, banner_window=0.05)
    adapter = MTPXAdapter(config, pool)
    try:
        channels = [{"input": i, "r": 0, "g": 0, "b": 31} for i in range(5, 13)]
        result = await adapter.execute("set_input_skew_batch", {"channels": channels})
        assert result.ok
        await asyncio.sleep(0.05)
        assert len(mtpx.commands) == 8
        assert mtpx.peak_concurrent == 8
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_exchange_single_roundtrips_on_a_lane(mtpx):
    pool = LanePoolTransport(mtpx.host, mtpx.port, lane_count=3, banner_window=0.05)
    try:
        reply = await pool.exchange("W5*0*0*31Iseq", terminator="\r\n")
        assert "Iseq05" in reply.response
    finally:
        await pool.aclose()


def test_registry_builds_lane_pool():
    config = DeviceConfig(device_id="device.mtpx.1", type="mtpx",
                          connection="lanes", lane_count=10)
    assert config.connection == "lanes" and config.lane_count == 10
