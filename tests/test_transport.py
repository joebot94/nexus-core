import pytest

from nexus.transports import TCPTransport, TransportError


@pytest.mark.asyncio
async def test_exchange_reads_banner_and_reply(fake_sis_server):
    host, port, _sim = fake_sis_server
    transport = TCPTransport(host, port, banner_window=0.15, read_timeout=1.0)
    reply = await transport.exchange("Q")
    assert "Extron Electronics" in reply.banner
    assert "MGP 464" in reply.banner
    assert reply.response == "1.12"
    assert reply.latency_ms >= 0


@pytest.mark.asyncio
async def test_connect_failure_raises_fast():
    # Port 1 on localhost: nothing listening — must fail loud, not hang.
    transport = TCPTransport("127.0.0.1", 1, connect_timeout=1.0)
    with pytest.raises(TransportError, match="connect failed"):
        await transport.exchange("Q")
