"""PooledTransport — persistent sockets, gap-aware recycle, retry-once on the
self-close race, unsolicited listening, and one-shot-compatible semantics.

The fixture server speaks MGP-flavored SIS and can be told to go silent, drop
a client mid-command (the ~310s self-close race, compressed), or volunteer an
unsolicited line to every open session.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from nexus.adapters.mgp import MGP464Adapter
from nexus.adapters.mtpx import MTPXAdapter
from nexus.registry import DeviceConfig
from nexus.transports import PooledTransport, PoolPolicy, TransportError


class RackSim:
    """Instrumented fake device on a real TCP socket."""

    def __init__(self) -> None:
        self.simulator = MGP464Adapter.Simulator()
        self.connects = 0
        self.commands: list[str] = []
        self.silent = False
        self.close_on: str | None = None   # drop the client on this command, once
        self._writers: list[asyncio.StreamWriter] = []
        self.host = ""
        self.port = 0
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.host, self.port = self._server.sockets[0].getsockname()[:2]

    async def stop(self) -> None:
        for writer in self._writers:
            writer.close()
        self._server.close()
        await self._server.wait_closed()

    async def volunteer(self, line: str) -> None:
        """Broadcast an unsolicited line to every open session."""
        for writer in self._writers:
            if not writer.is_closing():
                writer.write((line + "\r\n").encode())
                await writer.drain()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.connects += 1
        self._writers.append(writer)
        writer.write((self.simulator.banner + "\r\n").encode())
        await writer.drain()
        try:
            while True:
                data = await reader.readuntil(b"\r")
                command = data.decode().strip()
                if not command:
                    continue
                self.commands.append(command)
                if command == self.close_on:
                    self.close_on = None     # once: the reconnect must succeed
                    writer.close()
                    return
                if self.silent:
                    continue
                writer.write((self.simulator.respond(command) + "\r\n").encode())
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()


@pytest_asyncio.fixture
async def rack():
    sim = RackSim()
    await sim.start()
    yield sim
    await sim.stop()


def _pool(rack: RackSim, **policy) -> PooledTransport:
    return PooledTransport(rack.host, rack.port, policy=PoolPolicy(**policy))


@pytest.mark.asyncio
async def test_pool_reuses_one_connection(rack):
    pool = _pool(rack)
    try:
        for _ in range(3):
            reply = await pool.exchange("Q")
            assert reply.response == "1.12"
        assert rack.connects == 1
        assert pool.stats["connects"] == 1
        # No connect overhead on the held socket.
        assert "MGP 464" in (await pool.exchange("Q")).banner
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_idle_past_trust_window_recycles(rack):
    pool = _pool(rack, idle_recycle_s=0.15)
    try:
        await pool.exchange("Q")
        await asyncio.sleep(0.3)             # compressed ~310s idle
        reply = await pool.exchange("Q")     # must proactively reconnect
        assert reply.response == "1.12"
        assert rack.connects == 2
        assert pool.stats["recycles"] == 1
        assert pool.stats["retries"] == 0    # recycle is pre-send, not a failure
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_self_close_race_retries_once_transparently(rack):
    """The device closes the socket as our command lands (the 310s race):
    the pool must reconnect and resend, and the caller never notices."""
    pool = _pool(rack)
    try:
        await pool.exchange("Q")
        rack.close_on = "2*48."
        reply = await pool.exchange("2*48.")
        assert reply.response == "Rpr2*048"
        assert rack.connects == 2
        assert pool.stats["retries"] == 1
        assert rack.commands.count("2*48.") == 2   # dropped send + the retry
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_device_eof_while_idle_reconnects_on_next_send(rack):
    pool = _pool(rack)
    try:
        await pool.exchange("Q")
        await rack.stop()                    # device closes every session
        await asyncio.sleep(0.05)            # reader notices EOF
        assert not pool.connected
        await rack.start()                   # device comes back (new port!)
        pool.host, pool.port = rack.host, rack.port
        assert (await pool.exchange("Q")).response == "1.12"
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_silence_is_not_death(rack):
    """A quiet device (MTPX no-response mode) must yield the one-shot
    'no response' error WITHOUT burning the connection or retrying."""
    pool = _pool(rack, read_timeout=0.15)
    try:
        await pool.exchange("Q")
        rack.silent = True
        with pytest.raises(TransportError, match="no response"):
            await pool.exchange("Q")
        rack.silent = False
        assert (await pool.exchange("Q")).response == "1.12"
        assert rack.connects == 1            # same socket throughout
        assert pool.stats["retries"] == 0
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_batch_is_best_effort_and_silent_safe(rack):
    pool = _pool(rack)
    try:
        reply = await pool.exchange_batch(["2*48.", "2*52."], terminator="\r", drain=0.15)
        assert "Rpr2*048" in reply.response and "Rpr2*052" in reply.response
        rack.silent = True
        reply = await pool.exchange_batch(["2*48."], terminator="\r", drain=0.1)
        assert reply.response == ""          # silence is success on the batch path
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_sequence_pairs_each_command_with_its_reply(rack):
    pool = _pool(rack)
    try:
        replies = await pool.exchange_sequence(["1!", "2!", "Q"])
        assert [r.response for r in replies] == ["01", "02", "1.12"]
        assert rack.connects == 1
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_concurrent_exchanges_serialize_and_pair_correctly(rack):
    pool = _pool(rack)
    try:
        replies = await asyncio.gather(*[pool.exchange(f"{w}!") for w in (1, 2, 3, 4)],
                                       pool.exchange("Q"))
        assert [r.response for r in replies] == ["01", "02", "03", "04", "1.12"]
        assert rack.connects == 1
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_unsolicited_lines_reach_the_listener(rack):
    pool = _pool(rack)
    heard: list[str] = []
    pool.on_unsolicited = heard.append
    try:
        await pool.exchange("Q")             # opens the session
        await rack.volunteer("Rpr2*052")     # front-panel layout recall
        await asyncio.sleep(0.1)
        assert heard == ["Rpr2*052"]
        assert pool.stats["unsolicited"] == 1
        # …and the MGP adapter maps it to confirmed state.
        adapter = MGP464Adapter(DeviceConfig(device_id="d", type="mgp464"), pool)
        assert adapter.parse_unsolicited("Rpr2*052") == {"preset": 52}
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_keepalive_touches_an_idle_open_socket(rack):
    pool = _pool(rack, keepalive_s=0.15)
    try:
        await pool.exchange("Q")
        baseline = len(rack.commands)
        await asyncio.sleep(0.5)             # several keepalive windows
        assert len(rack.commands) > baseline  # Q keepalives flowed
        assert rack.connects == 1             # same session held open
    finally:
        await pool.aclose()


@pytest.mark.asyncio
async def test_aclose_then_reuse_reconnects(rack):
    pool = _pool(rack)
    await pool.exchange("Q")
    await pool.aclose()
    assert not pool.connected
    assert (await pool.exchange("Q")).response == "1.12"
    assert rack.connects == 2
    await pool.aclose()


def test_unsolicited_parsers_are_conservative():
    mgp = MGP464Adapter(DeviceConfig(device_id="m", type="mgp464"), None)
    assert mgp.parse_unsolicited("Rpr2*048") == {"preset": 48}
    assert mgp.parse_unsolicited("01") == {}                # bare route ack: ambiguous
    assert mgp.parse_unsolicited("garbage") == {}
    mtpx = MTPXAdapter(DeviceConfig(device_id="x", type="mtpx"), None)
    assert mtpx.parse_unsolicited("Iseq07 00 00 31") == {"input_7_skew": [0, 0, 31]}
    assert mtpx.parse_unsolicited("Rpr03") == {"preset": 3}  # family fallback
    assert mtpx.parse_unsolicited("") == {}


def test_registry_builds_pooled_transport():
    from nexus.adapters.mgp import MGP464Adapter as _  # noqa: F401
    config = DeviceConfig(device_id="device.mgp.pooled", type="mgp464",
                          host="10.0.0.63", connection="pooled",
                          idle_recycle_s=280.0, keepalive_s=240.0)
    assert config.connection == "pooled"
    # The full registry path is exercised via load(); here we check the policy
    # fields survive the model round-trip the .jbt file will do.
    assert DeviceConfig(**config.model_dump()).keepalive_s == 240.0
