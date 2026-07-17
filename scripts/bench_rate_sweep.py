#!/usr/bin/env python3
"""Bench rate sweep — find where fast switching goes clean → cool-glitchy → broken.

Fires an alternating A/B command pair at a device at increasing rates while the
operator watches the wall and grades each stage. The graded thresholds are the
real numbers for `MECHANISMS` in nexus/videowall.py (which today holds
placeholders everywhere except MGP input-remap ≈ 15 Hz).

Stdlib only, direct TCP — run it from any laptop on the rack LAN. Nothing here
goes through Nexus; this is a bench instrument, not a show path.

Modes (what alternates):
  dms-tie      DMS/matrix tie flip          A*OUT! / B*OUT!        (--a/--b inputs, --target output)
  mgp-input    MGP window input remap       A*WIN! / B*WIN!        (--a/--b inputs, --target window)
  mgp-preset   MGP layout preset flip       2*A.   / 2*B.          (--a/--b presets)
  custom       anything                     --wire-a / --wire-b verbatim

Examples:
  # Where does DMS→MGP DVI re-handshake stop being cool? Flip inputs 1/2 on output 5:
  scripts/bench_rate_sweep.py --host 10.0.0.13 --mode dms-tie --a 1 --b 2 --target 5

  # MGP window-move ceiling (window 1 flips between inputs 3 and 4):
  scripts/bench_rate_sweep.py --host 10.0.0.63 --mode mgp-input --a 3 --b 4 --target 1

  # Preset-recall stutter test:
  scripts/bench_rate_sweep.py --host 10.0.0.63 --mode mgp-preset --a 48 --b 52

Grades per stage: [c]lean  [g]litchy-cool  [b]roken  [r]epeat  [s]kip  [q]uit.
Writes a JSON report + prints the summary table and suggested MECHANISMS values.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from datetime import datetime, timezone

DEFAULT_RATES = [0.5, 1, 2, 4, 6, 8, 10, 12, 15, 20, 25, 30]
GRADES = {"c": "clean", "g": "glitchy-cool", "b": "broken"}


def build_wires(args: argparse.Namespace) -> tuple[str, str]:
    if args.mode == "dms-tie":
        return f"{args.a}*{args.target}!", f"{args.b}*{args.target}!"
    if args.mode == "mgp-input":
        return f"{args.a}*{args.target}!", f"{args.b}*{args.target}!"
    if args.mode == "mgp-preset":
        return f"2*{args.a}.", f"2*{args.b}."
    if args.mode == "custom":
        if not (args.wire_a and args.wire_b):
            sys.exit("custom mode needs --wire-a and --wire-b")
        return args.wire_a, args.wire_b
    sys.exit(f"unknown mode {args.mode}")


class Rig:
    """One persistent telnet-ish socket. Replies are drained, not awaited —
    at 20 Hz we care about send pacing, not ack round-trips."""

    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.settimeout(0.05)
        self.drain(1.0)  # connect banner (and password prompt — fail loud if so)

    def drain(self, window: float = 0.05) -> bytes:
        data = b""
        end = time.monotonic() + window
        while time.monotonic() < end:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("device closed the socket")
                data += chunk
            except socket.timeout:
                break
        if b"Password:" in data:
            sys.exit("device wants a password — clear it or bench a different unit")
        return data

    def fire(self, wire: str) -> None:
        self.sock.sendall(wire.encode("ascii") + b"\r")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def run_stage(rig: Rig, wire_a: str, wire_b: str, rate_hz: float, seconds: float) -> int:
    """Alternate A/B at rate_hz for `seconds`. Returns commands sent."""
    interval = 1.0 / rate_hz
    fires = max(2, int(seconds * rate_hz))
    start = time.monotonic()
    for n in range(fires):
        rig.fire(wire_a if n % 2 == 0 else wire_b)
        rig.drain(0.0)  # keep the receive buffer from backing up, never block
        next_at = start + (n + 1) * interval
        while (remaining := next_at - time.monotonic()) > 0:
            time.sleep(min(remaining, 0.01))
    rig.drain(0.2)
    return fires


def prompt_grade(rate_hz: float) -> str:
    while True:
        raw = input(f"  {rate_hz:g} Hz — [c]lean / [g]litchy-cool / [b]roken / "
                    f"[r]epeat / [s]kip / [q]uit: ").strip().lower()
        if raw in ("c", "g", "b", "r", "s", "q"):
            return raw
        print("  ? one of c/g/b/r/s/q")


def summarize(results: list[dict]) -> dict:
    graded = [r for r in results if r["grade"] in GRADES.values()]
    max_clean = max((r["rate_hz"] for r in graded if r["grade"] == "clean"), default=None)
    glitch = [r["rate_hz"] for r in graded if r["grade"] == "glitchy-cool"]
    min_broken = min((r["rate_hz"] for r in graded if r["grade"] == "broken"), default=None)
    return {
        "max_clean_hz": max_clean,
        "glitchy_cool_band_hz": [min(glitch), max(glitch)] if glitch else None,
        "min_broken_hz": min_broken,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=23)
    ap.add_argument("--mode", required=True,
                    choices=["dms-tie", "mgp-input", "mgp-preset", "custom"])
    ap.add_argument("--a", type=int, help="input/preset A")
    ap.add_argument("--b", type=int, help="input/preset B")
    ap.add_argument("--target", type=int, help="output (dms-tie) / window (mgp-input)")
    ap.add_argument("--wire-a", help="custom mode: verbatim SIS command A (no CR)")
    ap.add_argument("--wire-b", help="custom mode: verbatim SIS command B (no CR)")
    ap.add_argument("--rates", default=",".join(str(r) for r in DEFAULT_RATES),
                    help="comma-separated Hz stages (default: %(default)s)")
    ap.add_argument("--seconds", type=float, default=8.0, help="seconds per stage")
    ap.add_argument("--report", default=None,
                    help="JSON report path (default: bench_sweep_<mode>_<timestamp>.json)")
    args = ap.parse_args()

    if args.mode in ("dms-tie", "mgp-input") and None in (args.a, args.b, args.target):
        sys.exit(f"{args.mode} needs --a, --b, and --target")
    if args.mode == "mgp-preset" and None in (args.a, args.b):
        sys.exit("mgp-preset needs --a and --b")

    wire_a, wire_b = build_wires(args)
    rates = [float(r) for r in args.rates.split(",") if r.strip()]

    print(f"\nBench rate sweep — {args.mode} @ {args.host}:{args.port}")
    print(f"  A: {wire_a!r}   B: {wire_b!r}")
    print(f"  stages: {', '.join(f'{r:g}' for r in rates)} Hz × {args.seconds:g}s each")
    print("  Watch the wall. After each stage, grade what you saw.\n")

    rig = Rig(args.host, args.port)
    results: list[dict] = []
    try:
        for rate in rates:
            while True:
                print(f"  running {rate:g} Hz for {args.seconds:g}s …", flush=True)
                sent = run_stage(rig, wire_a, wire_b, rate, args.seconds)
                choice = prompt_grade(rate)
                if choice == "r":
                    continue
                if choice == "q":
                    raise KeyboardInterrupt
                if choice == "s":
                    results.append({"rate_hz": rate, "grade": "skipped", "commands": sent})
                else:
                    results.append({"rate_hz": rate, "grade": GRADES[choice], "commands": sent})
                break
            if results and results[-1]["grade"] == "broken":
                more = input("  broken — keep climbing anyway? [y/N]: ").strip().lower()
                if more != "y":
                    break
    except KeyboardInterrupt:
        print("\n  sweep stopped.")
    finally:
        rig.close()

    if not results:
        print("nothing graded, no report written.")
        return

    summary = summarize(results)
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host": args.host, "port": args.port, "mode": args.mode,
        "wire_a": wire_a, "wire_b": wire_b,
        "seconds_per_stage": args.seconds,
        "results": results, "summary": summary,
    }
    path = args.report or f"bench_sweep_{args.mode}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print("\n  rate     grade")
    for r in results:
        print(f"  {r['rate_hz']:>6g}   {r['grade']}")
    print(f"\n  max clean: {summary['max_clean_hz']} Hz"
          f" · cool band: {summary['glitchy_cool_band_hz']} Hz"
          f" · broken from: {summary['min_broken_hz']} Hz")
    print(f"  report: {path}")
    print("\n  → put max_clean into MECHANISMS max_hz (nexus/videowall.py); the cool "
          "band is the future 'overdrive' stutter range.")


if __name__ == "__main__":
    main()
