# Nexus Core — Status (honest ledger)

_Updated: 2026-07-10 (v0.2.0, M2 first wave)_

## v0.2.0 — M2 first wave

- **Three-client day**: the same MGP was driven via curl, the desktop
  GlitchBoard "Nexus API" connection type, and the ported iPad GlitchBoard
  (preset 52 from the iPad, 2026-07-10 19:58 in the event log) — none of
  them speaking SIS.
- **New adapters**: Matrix 12800 (tie/untie/query per deployed lab code),
  SMX (RprNN presets — the family exception —, plane ties `PP*in*out&/$`),
  DMS 3600 (36×24 ties), and generic **`extron_sis`** so any Extron box can
  join with just a registry entry.
- **Transport handles login prompts** (Matrix/SMX may ask; answers like the
  lab's handshake, admin/admin fallback).
- **`POST /api/v1/registry/reload`** — add devices without a restart;
  malformed/unknown entries skip with warnings instead of crashing.
- **Web client is capability-driven** — buttons come from `/capabilities`,
  so new device types get working controls with zero client changes.
- **Live rack sweep (read-only, 2026-07-10 ~23:00)**: MGP online (fw 1.12);
  **SMX @ 10.0.0.11 is BACK ONLINE** (fw 1.20, 3–5ms) — live tie queries
  verified on planes 00/02/04 (input 5 → output 1); Matrix 12800 and
  DMS 3600 currently unreachable (marked offline honestly). No mutating
  command was sent — operator wasn't watching the rack.
- SMX preset recall + ties and Matrix/DMS actions are **wire-verified against
  deployed lab code but not yet live-fired** (SMX presets change routing!).

## Verdict on the prior Python Nexus

**Superseded as a codebase, retained as a design.** The old
`joebot-ecosystem/nexus` was an app-to-app message bus with zero device
control (adapters were explicitly deferred in its build prompt and never
happened). Its concepts — registry, capabilities, event recording, scenes —
inform this service; its coordination features return in a later milestone.
Device-control code was instead re-homed conceptually from **joebot-lab**
(the NAS dashboard) and from GlitchBoard's live-verified wire work.

## What works, real vs simulated

| Piece | Status |
|---|---|
| REST /api/v1 (health, devices, state, capabilities, probe, actions, events, raw) | **Real**, integration-tested |
| WebSocket event stream | **Real**, exercised by the built-in web client |
| `.jbt` registry bootstrap + rolling event log | **Real** |
| Token auth (`NEXUS_TOKEN`) | **Real**, tested; disabled by default on trusted LAN |
| TCP SIS transport (CR out / CRLF in / banner drain) | **Real** — tested against a fake SIS device over real sockets; semantics ported from the TCPTransport.swift that was verified on the live MGP |
| MGP 464 adapter: `recall_preset` (`2*NN.`→`Rpr2*NNN.`), `route_input_to_window`, `query_window`, `query_firmware` | **Real commands, live-verified syntax** (July 2026 GlitchBoard sessions) |
| `device.mgp.sim` | **Simulated** (same adapter + API path, SimTransport only) |
| Live rig verification | Probe (`Q`) against MGP @ 10.0.0.63 — see below |

## Live hardware log

- **2026-07-10 — first live contact through the full stack.** MGP 464 Pro DI
  @ 10.0.0.63:23, via `POST /probe` and `POST /actions`:
  - probe: online, model "MGP 464 Pro DI" parsed from banner, fw 1.12, 16 ms
  - `query_window {window: 1}` → `01` → state `window_1=1` (source: query), 17–19 ms
  - exercised from both curl and the built-in web client; WS event stream
    carried every result live
- **2026-07-10 — first live mutating action, operator watching.**
  `recall_preset {preset: 48}` → `2*48.` → ack `Rpr2*048`, 75 ms,
  state `preset=48` (source: command_ack). The vertical slice is fully
  live-verified end to end: normalized action → SIS translation → real
  hardware → parsed ack → state store → WebSocket broadcast.

## Known limits (v1, by design)

- One-shot connect-per-command (~40–70 ms vs live MGP). Pooling = M4.
- No polling loop — state updates only from acks/probes/queries.
- No unsolicited-response listening (needs persistent connections, M4).
- Groups endpoint returns `[]` (shape reserved, lands M2).
- Coordination plane (app registration, intents, scenes, recording) not
  started — later milestone, per the locked plan.
