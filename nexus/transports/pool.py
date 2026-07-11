"""Persistent per-device connection — M4 connection ownership.

Why pooling: the one-shot transport pays a fresh TCP connect + banner window
per command (~40-70 ms against the live MGP). A held socket answers in
single-digit ms, and it is the ONLY way to hear unsolicited traffic — the
front-panel/other-session change broadcasts an open session receives.

Measured device behavior this encodes (July 2026, live MGP 464):
  - the box self-closes an idle session at ~310 s
  - traffic resets that timer (so a periodic keepalive holds it open)
  - 4+ concurrent sessions are fine (GlitchBoard direct + Nexus coexist)

Policy, not heroics:
  - a connection idle past `idle_recycle_s` (default 280 s, safely under the
    self-close) is presumed dead and replaced BEFORE the next send
  - a send that discovers a dead socket (EOF mid-exchange — the self-close
    race) reconnects and retries ONCE
  - silence from a device that is merely quiet (MTPX no-response mode) is
    NOT a failure and never triggers a retry — one-shot semantics preserved
  - keepalive is opt-in (`keepalive_s` > 0) and only maintains an already-
    open connection; it never dials a dark device in a loop

Drop-in: implements the same exchange / exchange_batch / exchange_sequence
surface as TCPTransport, so adapters don't know which one they're on.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable

from .tcp import TransportError, TransportReply


class _ConnectionLost(Exception):
    """The socket died while an exchange was in flight (retry-once signal)."""


@dataclass
class PoolPolicy:
    idle_recycle_s: float = 280.0   # replace a socket idle past this (MGP ~310s)
    keepalive_s: float = 0.0        # 0 = off; else send keepalive_wire when idle
    keepalive_wire: str = "Q"       # read-only identity query, same as probe
    connect_timeout: float = 3.0
    banner_window: float = 0.5
    read_timeout: float = 2.0


class _Waiter:
    """One in-flight exchange's reply collector.

    mode "line": the reader resolves `done` at the first CRLF (a normal SIS
    reply). mode "window": `done` resolves only on connection loss — the
    exchange just collects whatever arrives during its drain window (the
    best-effort batch path a silent MTPX needs).
    """

    __slots__ = ("mode", "buf", "done")

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.buf = bytearray()
        self.done: asyncio.Future = asyncio.get_running_loop().create_future()


class PooledTransport:
    def __init__(self, host: str, port: int = 23, *, username: str = "",
                 password: str = "", policy: PoolPolicy | None = None) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.policy = policy or PoolPolicy()
        # Called with each complete line that arrives while NO exchange is in
        # flight — front-panel changes, other sessions' echoes. Wired by the
        # app to adapter.parse_unsolicited → state store.
        self.on_unsolicited: Callable[[str], None] | None = None
        self.stats = {"connects": 0, "recycles": 0, "retries": 0, "unsolicited": 0}
        self._lock = asyncio.Lock()          # serializes all exchanges
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._pending: _Waiter | None = None
        self._unsol = bytearray()
        self._banner = ""
        self._last_activity = 0.0

    @property
    def connected(self) -> bool:
        return self._writer is not None

    # ---- public transport surface (mirrors TCPTransport) -------------------

    async def exchange(self, command: str, terminator: str = "\r") -> TransportReply:
        async with self._lock:
            return await self._with_retry(lambda: self._locked_line(command, terminator))

    async def exchange_sequence(self, commands: list[str],
                                terminator: str = "\r") -> list[TransportReply]:
        """One reply per command over the held socket. On a mid-sequence
        connection loss the WHOLE sequence restarts once — callers use this
        for read-only queries (name banks), where a re-read is harmless."""
        if not commands:
            return []

        async def run() -> list[TransportReply]:
            return [await self._locked_line(c, terminator) for c in commands]

        async with self._lock:
            return await self._with_retry(run)

    async def exchange_batch(self, commands: list[str], terminator: str = "\r\n",
                             drain: float = 0.3) -> TransportReply:
        """Write several commands, then best-effort drain. Success = the write
        completed; silence is fine (MTPX no-response mode). Retried once only
        on connection loss — skew/peaking sets are idempotent."""
        if not commands:
            return TransportReply(banner="", response="", raw=b"", latency_ms=0)

        async def run() -> TransportReply:
            if self._writer is None:   # EOF landed between ensure and write
                raise _ConnectionLost("not connected")
            waiter = _Waiter("window")
            self._pending = waiter
            start = time.monotonic()
            try:
                blob = "".join(c + terminator for c in commands)
                self._writer.write(blob.encode())
                await self._writer.drain()
                self._last_activity = time.monotonic()
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(waiter.done, drain)  # resolves only on loss
                raw = bytes(waiter.buf)
                return TransportReply(
                    banner=self._banner,
                    response=raw.decode(errors="replace").strip(),
                    raw=raw,
                    latency_ms=int((time.monotonic() - start) * 1000))
            finally:
                self._pending = None

        async with self._lock:
            return await self._with_retry(run)

    async def aclose(self) -> None:
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._keepalive_task
            self._keepalive_task = None
        async with self._lock:
            await self._close_connection()

    # ---- the retry-once shell ----------------------------------------------

    async def _with_retry(self, run):
        """Ensure a fresh connection, run the exchange, and on connection loss
        (never on mere silence) reconnect and retry exactly once."""
        await self._ensure_connection()
        for attempt in (1, 2):
            try:
                return await run()
            except (_ConnectionLost, ConnectionError, OSError) as exc:
                await self._close_connection()
                if attempt == 2:
                    raise TransportError(
                        f"connection lost: {str(exc) or type(exc).__name__}") from exc
                self.stats["retries"] += 1
                await self._connect()

    async def _locked_line(self, command: str, terminator: str) -> TransportReply:
        """One command → one CRLF-terminated reply. Caller holds the lock."""
        if self._writer is None:   # EOF landed between ensure and write
            raise _ConnectionLost("not connected")
        waiter = _Waiter("line")
        self._pending = waiter
        start = time.monotonic()
        try:
            self._writer.write((command + terminator).encode())
            await self._writer.drain()
            self._last_activity = time.monotonic()
            try:
                await asyncio.wait_for(waiter.done, self.policy.read_timeout)
            except asyncio.TimeoutError:
                # Same semantics as the one-shot _read_line: whatever partial
                # data arrived is the reply; nothing at all is "no response"
                # (a quiet device, NOT a dead socket — no retry).
                if not waiter.buf:
                    raise TransportError("no response") from None
            raw = bytes(waiter.buf)
            return TransportReply(
                banner=self._banner,
                response=raw.decode(errors="replace").strip(),
                raw=raw,
                latency_ms=int((time.monotonic() - start) * 1000))
        finally:
            self._pending = None

    # ---- connection lifecycle ----------------------------------------------

    async def _ensure_connection(self) -> None:
        if self._writer is not None and \
                (time.monotonic() - self._last_activity) > self.policy.idle_recycle_s:
            # Past the trust window — the device may have self-closed and the
            # FIN might still be in flight. Replace proactively.
            self.stats["recycles"] += 1
            await self._close_connection()
        if self._writer is None:
            await self._connect()

    async def _connect(self) -> None:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.policy.connect_timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            raise TransportError(
                f"connect failed: {str(exc) or 'timed out / unreachable'}") from exc
        # Handshake inline (reader task not running yet): banner + any prompt,
        # identical to the one-shot transport's verified behavior.
        banner = await self._read_window(reader, self.policy.banner_window)
        prompt = banner.decode(errors="replace").lower()
        for needle, credential in (("password", self.password or "admin"),
                                   ("login", self.username or "admin")):
            if needle in prompt:
                writer.write((credential + "\r").encode())
                await writer.drain()
                banner = await self._read_window(reader, 0.4)
                prompt = banner.decode(errors="replace").lower()
        self._reader, self._writer = reader, writer
        self._banner = banner.decode(errors="replace").strip()
        self._last_activity = time.monotonic()
        self.stats["connects"] += 1
        self._reader_task = asyncio.create_task(self._read_loop(reader, writer))
        if self.policy.keepalive_s > 0 and self._keepalive_task is None:
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def _close_connection(self) -> None:
        task, self._reader_task = self._reader_task, None
        writer, self._writer, self._reader = self._writer, None, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        if writer is not None:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
        self._unsol.clear()

    # ---- background tasks ----------------------------------------------------

    async def _read_loop(self, reader: asyncio.StreamReader,
                         writer: asyncio.StreamWriter) -> None:
        """The single reader. Data goes to the in-flight exchange if there is
        one; otherwise it's unsolicited. EOF fails any pending exchange (so it
        can retry) and marks the pool disconnected."""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                self._last_activity = time.monotonic()
                waiter = self._pending
                if waiter is not None:
                    waiter.buf += chunk
                    if waiter.mode == "line" and b"\r\n" in waiter.buf \
                            and not waiter.done.done():
                        waiter.done.set_result(None)
                else:
                    self._feed_unsolicited(chunk)
        except asyncio.CancelledError:
            raise
        except OSError:
            pass
        finally:
            waiter = self._pending
            if waiter is not None and not waiter.done.done():
                waiter.done.set_exception(_ConnectionLost("socket closed mid-exchange"))
            # Only clear the pool's refs if they still point at THIS socket —
            # a recycle may already have installed a fresh connection.
            if self._writer is writer:
                self._writer = None
                self._reader = None
            writer.close()

    def _feed_unsolicited(self, chunk: bytes) -> None:
        self._unsol += chunk
        while (idx := self._unsol.find(b"\r\n")) != -1:
            line = self._unsol[:idx].decode(errors="replace").strip()
            del self._unsol[:idx + 2]
            if not line:
                continue
            self.stats["unsolicited"] += 1
            if self.on_unsolicited is not None:
                try:
                    self.on_unsolicited(line)
                except Exception:
                    pass  # a listener bug must never kill the reader

    async def _keepalive_loop(self) -> None:
        """Hold an OPEN connection open by touching it before the device's
        idle self-close. Never dials out — a dark or closed device stays
        untouched until the next real command."""
        check_every = max(0.05, min(self.policy.keepalive_s / 4, 30.0))
        while True:
            await asyncio.sleep(check_every)
            if self._writer is None:
                continue
            if (time.monotonic() - self._last_activity) < self.policy.keepalive_s:
                continue
            with suppress(TransportError, Exception):
                await self.exchange(self.policy.keepalive_wire)

    @staticmethod
    async def _read_window(reader: asyncio.StreamReader, window: float) -> bytes:
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
