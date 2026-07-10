"""One-shot Extron SIS exchange over TCP.

Wire behavior mirrors GlitchBoard's TCPTransport.swift, which was verified
against the live MGP 464 Pro at 10.0.0.63: commands terminate with CR,
replies terminate with CRLF, and the device volunteers a copyright/model/
firmware banner on connect (no password prompt when none is set).

No persistent sockets yet — connection pooling with per-device recycle
policy (Extron boxes self-close at ~310s idle) is milestone M4.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Protocol


@dataclass
class TransportReply:
    banner: str        # greeting the device volunteered on connect
    response: str      # trimmed reply to the command we sent
    raw: bytes
    latency_ms: int


class TransportError(Exception):
    pass


class Transport(Protocol):
    async def exchange(self, command: str, terminator: str = "\r") -> TransportReply: ...


class TCPTransport:
    def __init__(self, host: str, port: int = 23, *, connect_timeout: float = 3.0,
                 banner_window: float = 0.5, read_timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.banner_window = banner_window
        self.read_timeout = read_timeout

    async def exchange(self, command: str, terminator: str = "\r") -> TransportReply:
        """Open → drain banner → send one command → read one CRLF reply → close."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.connect_timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            raise TransportError(f"connect failed: {exc or 'timed out'}") from exc
        try:
            banner = await self._read_window(reader, self.banner_window)
            start = time.monotonic()
            writer.write((command + terminator).encode())
            await writer.drain()
            raw = await self._read_line(reader, self.read_timeout)
            latency = int((time.monotonic() - start) * 1000)
            return TransportReply(
                banner=banner.decode(errors="replace").strip(),
                response=raw.decode(errors="replace").strip(),
                raw=raw,
                latency_ms=latency,
            )
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    @staticmethod
    async def _read_window(reader: asyncio.StreamReader, window: float) -> bytes:
        """Best-effort read for a fixed window — some devices stay silent."""
        buf = b""
        deadline = time.monotonic() + window
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), remaining)
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            buf += chunk
        return buf

    @staticmethod
    async def _read_line(reader: asyncio.StreamReader, timeout: float) -> bytes:
        """Accumulate chunks until CRLF or deadline."""
        buf = b""
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), remaining)
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            buf += chunk
            if b"\r\n" in buf:
                break
        if not buf:
            raise TransportError("no response")
        return buf


class SimTransport:
    """Same interface as TCPTransport, answered by an adapter-supplied simulator.

    Simulation follows the same adapter and API path as real hardware — only
    this class is swapped, per the vertical-slice requirement.
    """

    def __init__(self, simulator) -> None:
        self.simulator = simulator

    async def exchange(self, command: str, terminator: str = "\r") -> TransportReply:
        await asyncio.sleep(0.005)
        response = self.simulator.respond(command.strip())
        return TransportReply(
            banner=self.simulator.banner,
            response=response,
            raw=(response + "\r\n").encode(),
            latency_ms=5,
        )
