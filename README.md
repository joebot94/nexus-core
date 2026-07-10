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
