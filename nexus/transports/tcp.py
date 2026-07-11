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
    async def exchange_sequence(self, commands: list[str], terminator: str = "\r") -> list[TransportReply]: ...


class TCPTransport:
    def __init__(self, host: str, port: int = 23, *, username: str = "", password: str = "",
                 connect_timeout: float = 3.0, banner_window: float = 0.5,
                 read_timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.connect_timeout = connect_timeout
        self.banner_window = banner_window
        self.read_timeout = read_timeout

    async def exchange(self, command: str, terminator: str = "\r") -> TransportReply:
        """Open → drain banner (answering any login prompt) → send one command →
        read one CRLF reply → close."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.connect_timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            raise TransportError(f"connect failed: {str(exc) or 'timed out / unreachable'}") from exc
        try:
            banner = await self._read_window(reader, self.banner_window)
            # Some Extron boxes (Matrix 12800, SMX) prompt before the banner.
            # Mirrors the deployed joebot-lab _open() handshake.
            prompt = banner.decode(errors="replace").lower()
            for needle, credential in (("password", self.password or "admin"),
                                       ("login", self.username or "admin")):
                if needle in prompt:
                    writer.write((credential + "\r").encode())
                    await writer.drain()
                    banner = await self._read_window(reader, 0.4)
                    prompt = banner.decode(errors="replace").lower()
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

    async def exchange_batch(self, commands: list[str], terminator: str = "\r\n",
                             drain: float = 0.3) -> TransportReply:
        """Write several commands in ONE connection, then best-effort drain.

        Mirrors GlitchBoard's verified sendBatch: success = the write completed.
        A reply is NOT required — the MTPX in no-response mode stays silent, and
        that is still a successful send. Whatever does echo back is returned
        (concatenated) for diagnostics/confirmation. Raises only on connect
        failure, never on silence.
        """
        if not commands:
            return TransportReply(banner="", response="", raw=b"", latency_ms=0)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.connect_timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            raise TransportError(f"connect failed: {str(exc) or 'timed out / unreachable'}") from exc
        try:
            banner = await self._read_window(reader, self.banner_window)
            prompt = banner.decode(errors="replace").lower()
            for needle, credential in (("password", self.password or "admin"),
                                       ("login", self.username or "admin")):
                if needle in prompt:
                    writer.write((credential + "\r").encode())
                    await writer.drain()
                    await self._read_window(reader, 0.4)
            start = time.monotonic()
            blob = "".join(c + terminator for c in commands)
            writer.write(blob.encode())
            await writer.drain()
            echoed = await self._read_window(reader, drain)   # best-effort
            latency = int((time.monotonic() - start) * 1000)
            return TransportReply(
                banner=banner.decode(errors="replace").strip(),
                response=echoed.decode(errors="replace").strip(),
                raw=echoed,
                latency_ms=latency,
            )
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def exchange_sequence(self, commands: list[str], terminator: str = "\r") -> list[TransportReply]:
        """Send read/query commands one at a time over ONE authenticated socket.

        Name-bank sync uses this rather than reconnecting once per channel. Each
        command still gets its own reply, unlike `exchange_batch`, so callers
        can safely pair a channel number with its returned label.
        """
        if not commands:
            return []
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.connect_timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            raise TransportError(f"connect failed: {str(exc) or 'timed out / unreachable'}") from exc
        try:
            banner_raw = await self._read_window(reader, self.banner_window)
            banner = banner_raw.decode(errors="replace").strip()
            prompt = banner.lower()
            for needle, credential in (("password", self.password or "admin"),
                                       ("login", self.username or "admin")):
                if needle in prompt:
                    writer.write((credential + "\r").encode())
                    await writer.drain()
                    banner = (await self._read_window(reader, 0.4)).decode(errors="replace").strip()
                    prompt = banner.lower()
            replies: list[TransportReply] = []
            for command in commands:
                start = time.monotonic()
                writer.write((command + terminator).encode())
                await writer.drain()
                raw = await self._read_line(reader, self.read_timeout)
                replies.append(TransportReply(
                    banner=banner, response=raw.decode(errors="replace").strip(), raw=raw,
                    latency_ms=int((time.monotonic() - start) * 1000)))
            return replies
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

    async def exchange_batch(self, commands: list[str], terminator: str = "\r\n",
                             drain: float = 0.3) -> TransportReply:
        await asyncio.sleep(0.005)
        # Echo whatever the simulated device answers (some commands stay silent).
        echoes = [r for r in (self.simulator.respond(c.strip()) for c in commands) if r]
        return TransportReply(
            banner=self.simulator.banner,
            response="\r\n".join(echoes),
            raw=("\r\n".join(echoes) + "\r\n").encode(),
            latency_ms=5,
        )

    async def exchange_sequence(self, commands: list[str], terminator: str = "\r") -> list[TransportReply]:
        return [await self.exchange(command, terminator) for command in commands]
