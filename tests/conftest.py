"""Shared fixtures: a fake Extron SIS device on a real TCP socket."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from nexus.adapters.mgp import MGP464Adapter


@pytest_asyncio.fixture
async def fake_sis_server():
    """Real TCP server speaking MGP-flavored SIS: banner on connect, CR-terminated
    commands in, CRLF-terminated replies out. Yields (host, port, simulator)."""
    simulator = MGP464Adapter.Simulator()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        writer.write((simulator.banner + "\r\n").encode())
        await writer.drain()
        try:
            while True:
                data = await reader.readuntil(b"\r")
                command = data.decode().strip()
                response = simulator.respond(command)
                writer.write((response + "\r\n").encode())
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    yield host, port, simulator
    server.close()
    await server.wait_closed()
