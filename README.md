# Nexus Core 🦖

Central hardware abstraction service for the Joebot AV lab.
**Apps speak Nexus. Nexus speaks hardware. Users see magic.**

Clients send normalized actions to a stable API; Nexus translates them into
the correct protocol and syntax for the target device, parses the reply,
tracks state, and broadcasts events. No client ever builds a wire string.

```
POST /api/v1/actions
{ "target": "device.mgp.1", "action": "recall_preset", "parameters": { "preset": 48 } }
        │
        ▼
Nexus resolves device.mgp.1 → MGP464Adapter → sends `2*48.` over TCP :23
→ parses ack `Rpr2*048` → updates state → broadcasts on WebSocket → returns:
{ "ok": true, "response": "Rpr2*048", "state": { "preset": 48 }, "latency_ms": 42 }
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m nexus
```

Open **http://localhost:8675/** for the built-in test client,
**/docs** for interactive OpenAPI. That's the whole deployment story —
one Python process, config bootstraps itself on first run.

- Port is **8675** (Jenny 📞 — never 8765).
- Device registry: `data/jbt/device_registry.jbt` (`.jbt` mandate honored —
  edit it, restart, done).
- `NEXUS_SIMULATE=1` forces every device into simulation; per-device
  `"simulate": true` in the registry does it selectively. Simulation follows
  the exact same adapter and API path as real hardware.
- `NEXUS_TOKEN=...` enables LAN auth (send `X-Nexus-Token` or `Bearer`).

## Docker (NAS)

```bash
docker compose up -d --build     # host networking, persists ./data
```

See [docs/NEXUS-DEPLOYMENT.md](docs/NEXUS-DEPLOYMENT.md) for the Synology steps.

## Why a new repo (and what happened to the old Nexus)

The original [`joebot94/nexus`](https://github.com/joebot94/nexus) is an
**app-to-app WebSocket message bus** — registration, heartbeats, intents,
scenes, session recording. It was built exactly to its Phase-1 prompt, which
explicitly deferred hardware adapters to "a future session." That session
never happened, so the old Nexus never spoke to a single device.

Meanwhile the actual device-control code grew up elsewhere: the
**joebot-lab** NAS dashboard proved the SIS transports and polling, and
**GlitchBoard** live-verified the wire protocols against the real rack
(MGP `2*NN.` preset recall, MTPX `W…Iseq` skew, CR/CRLF framing, banner
formats, idle timeouts).

Nexus Core is the deliberate merge of those threads: the *vision* of the
old Nexus ("apps speak Nexus, Nexus speaks hardware"), the *protocol truth*
from the live-verified July 2026 work, and a clean device-plane-first
codebase built for headless NAS Docker duty. The old repo stays as-is —
its coordination features (scenes, intents, session recording) return here
as a later milestone. Full lineage table and the protocol truth hierarchy:
[docs/NEXUS-ARCHITECTURE.md](docs/NEXUS-ARCHITECTURE.md).

## Docs

| Doc | What |
|---|---|
| [NEXUS-ARCHITECTURE.md](docs/NEXUS-ARCHITECTURE.md) | design, adapter model, state model, planes |
| [NEXUS-API.md](docs/NEXUS-API.md) | endpoints + Python / Swift / JS examples |
| [NEXUS-STATUS.md](docs/NEXUS-STATUS.md) | what's real vs simulated, honestly |
| [NEXUS-DEPLOYMENT.md](docs/NEXUS-DEPLOYMENT.md) | local, Docker, NAS |
| [NEXUS-NEXT.md](docs/NEXUS-NEXT.md) | milestones M2–M4 and beyond |
| docs/reference/ | the March 2026 ecosystem docs (architecture, JBT, SIS) |

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Adapter tests run against a fake SIS device on a real TCP socket — the full
wire path (banner, CR/CRLF framing, ack parsing) without hardware.
