"""Parallel lane pool — many concurrent sockets to one device.

Ported in spirit from Joe's MTPXControl `MTPXNetworkService`: the MTPX fires a
big skew burst fastest when the commands are spread across several TCP
connections ("lanes") writing at once, rather than serialized through a single
socket. Each `W{in}*{r}*{g}*{b}Iseq` is independent (per-input), so parallel
dispatch is safe and there's no ordering to preserve.

Contrast with `PooledTransport` (one held socket, serialized, unsolicited
listening) — that's right for the stateful MGP. This is right for the MTPX:
fire-and-forget, no per-command wait (the unit is often in no-response mode, so
a completed WRITE is the success signal), lanes drained best-effort.

Interface-compatible with the other transports (`exchange` /
`exchange_batch` / `exchange_sequence`), so adapters don't change: the MTPX
adapter's `exchange_batch` skew path automatically fans across lanes when the
device's registry `connection` is `"lanes"`.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress

from .tcp import TransportError, TransportReply


class _Lane:
    __slots__ = ("reader", "writer", "banner")

    def __init__(self, reader, writer, banner: str) -> None:
        self.reader = reader
        self.writer = writer
        self.banner = banner

    @property
    def alive(self) -> bool:
        return self.writer is not None and not self.writer.is_closing()


class LanePoolTransport:
    def __init__(self, host: str, port: int = 23, *, username: str = "",
                 password: str = "", lane_count: int = 10,
                 connect_timeout: float = 3.0, banner_window: float = 0.5,
                 read_timeout: float = 2.0, drain: float = 0.3) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.lane_count = max(1, min(32, lane_count))
        self.connect_timeout = connect_timeout
        self.banner_window = banner_window
        self.read_timeout = read_timeout
        self.drain = drain
        self._lanes: list[_Lane] = []
        self._lock = asyncio.Lock()     # guards lane setup + round-robin index
        self._rr = 0
        self.stats = {"lane_opens": 0, "batches": 0, "commands": 0, "lane_drops": 0}

    @property
    def connected(self) -> bool:
        return any(l.alive for l in self._lanes)

    # ---- public transport surface -----------------------------------------

    async def exchange(self, command: str, terminator: str = "\r") -> TransportReply:
        """One command + one CRLF reply, on the next round-robin lane."""
        lane = await self._next_lane()
        return await self._line_exchange(lane, command, terminator)

    async def exchange_sequence(self, commands: list[str],
                                terminator: str = "\r") -> list[TransportReply]:
        """Ordered read/query commands over ONE lane (each paired with its
        reply) — reads must not be split across lanes."""
        if not commands:
            return []
        lane = await self._next_lane()
        return [await self._line_exchange(lane, c, terminator) for c in commands]

    async def exchange_batch(self, commands: list[str], terminator: str = "\r\n",
                             drain: float | None = None) -> TransportReply:
        """The performance path: spread the commands across all live lanes and
        write them concurrently. Best-effort — success is the writes completing,
        not a reply (MTPX no-response mode). Whatever echoes back is drained and
        concatenated for diagnostics. Raises only if no lane can be opened."""
        if not commands:
            return TransportReply(banner="", response="", raw=b"", latency_ms=0)
        await self._ensure_lanes()
        lanes = [l for l in self._lanes if l.alive]
        if not lanes:
            raise TransportError("no live lanes")

        # Round-robin the commands into one chunk per lane, so a burst of M
        # commands leaves in ~M/len(lanes) serial writes.
        chunks: list[list[str]] = [[] for _ in lanes]
        for i, command in enumerate(commands):
            chunks[i % len(lanes)].append(command)

        drain_s = self.drain if drain is None else drain
        start = time.monotonic()
        results = await asyncio.gather(
            *(self._write_chunk(lane, chunk, terminator, drain_s)
              for lane, chunk in zip(lanes, chunks) if chunk),
            return_exceptions=True)
        latency = int((time.monotonic() - start) * 1000)

        echoes: list[str] = []
        any_ok = False
        for lane, result in zip(lanes, results):
            if isinstance(result, Exception):
                self._drop(lane)
            else:
                any_ok = True
                if result:
                    echoes.append(result)
        if not any_ok:
            raise TransportError("all lanes failed mid-burst")

        self.stats["batches"] += 1
        self.stats["commands"] += len(commands)
        blob = "\r\n".join(e for e in echoes if e)
        return TransportReply(banner=lanes[0].banner, response=blob.strip(),
                              raw=blob.encode(), latency_ms=latency)

    async def aclose(self) -> None:
        async with self._lock:
            for lane in self._lanes:
                self._close_lane(lane)
            self._lanes.clear()

    # ---- lane lifecycle ----------------------------------------------------

    async def _ensure_lanes(self) -> None:
        if any(l.alive for l in self._lanes):
            return
        async with self._lock:
            if any(l.alive for l in self._lanes):
                return
            self._lanes = []
            opened = await asyncio.gather(
                *(self._open_lane() for _ in range(self.lane_count)),
                return_exceptions=True)
            self._lanes = [l for l in opened if isinstance(l, _Lane)]
            if not self._lanes:
                # Surface the first real connect error.
                first = next((r for r in opened if isinstance(r, Exception)), None)
                raise TransportError(f"no lanes opened: {first}")

    async def _next_lane(self) -> _Lane:
        await self._ensure_lanes()
        async with self._lock:
            live = [l for l in self._lanes if l.alive]
            if not live:
                raise TransportError("no live lanes")
            self._rr = (self._rr + 1) % len(live)
            return live[self._rr]

    async def _open_lane(self) -> _Lane:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.connect_timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            raise TransportError(
                f"connect failed: {str(exc) or 'timed out / unreachable'}") from exc
        banner = await self._read_window(reader, self.banner_window)
        prompt = banner.decode(errors="replace").lower()
        for needle, credential in (("password", self.password or "admin"),
                                   ("login", self.username or "admin")):
            if needle in prompt:
                writer.write((credential + "\r").encode())
                await writer.drain()
                banner = await self._read_window(reader, 0.4)
                prompt = banner.decode(errors="replace").lower()
        self.stats["lane_opens"] += 1
        return _Lane(reader, writer, banner.decode(errors="replace").strip())

    def _drop(self, lane: _Lane) -> None:
        self._close_lane(lane)
        self.stats["lane_drops"] += 1

    def _close_lane(self, lane: _Lane) -> None:
        if lane.writer is not None:
            lane.writer.close()
            lane.writer = None  # type: ignore[assignment]

    # ---- io helpers --------------------------------------------------------

    async def _write_chunk(self, lane: _Lane, chunk: list[str],
                           terminator: str, drain_s: float) -> str:
        """Chained single write of this lane's share, then a best-effort drain."""
        blob = "".join(c + terminator for c in chunk)
        lane.writer.write(blob.encode())
        await lane.writer.drain()
        echoed = await self._read_window(lane.reader, drain_s)
        return echoed.decode(errors="replace").strip()

    async def _line_exchange(self, lane: _Lane, command: str,
                             terminator: str) -> TransportReply:
        start = time.monotonic()
        lane.writer.write((command + terminator).encode())
        await lane.writer.drain()
        raw = await self._read_line(lane.reader, self.read_timeout)
        return TransportReply(banner=lane.banner,
                              response=raw.decode(errors="replace").strip(),
                              raw=raw, latency_ms=int((time.monotonic() - start) * 1000))

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

    @staticmethod
    async def _read_line(reader: asyncio.StreamReader, timeout: float) -> bytes:
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
