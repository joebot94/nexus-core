# Nexus Core — Status (honest ledger)

_Updated: 2026-07-10 (v0.3.0, MTPX adapter)_

## v0.3.0 — MTPX Plus adapter (the glitch technique)

- **MTPX adapter** (`nexus/adapters/mtpx.py`): input RGB skew
  `W{in}*{r}*{g}*{b}Iseq`, batch skew (many channels, ONE connection —
  the performance path), reset skew, output peaking `W{out}*{0|1}Opek`,
  universal preset recall — all **`verified=True`** (live-verified command
  forms from GlitchBoard/MTPXControl). Crosspoint ties + `S` system status
  are **`verified=False`** (doc-only, not bench-tested on these units).
- **Best-effort batch transport** (`exchange_batch`): mirrors GlitchBoard's
  verified `sendBatch` — a skew send SUCCEEDS when the write completes, even
  if the MTPX (in no-response mode) stays silent. When it does echo, state is
  upgraded from `inferred` to confirmed `command_ack`. A powered-off unit
  (connect fails) correctly reports `ok:false`, never a fake success.
- **Registry**: `device.mtpx.1` (1616 @ .15), `device.mtpx.2` (128 @ .16,
  inputs 5-12 skewable), `device.mtpx.sim`. IPs flagged unconfirmed in notes.
- **Web client** gained skew/reset controls automatically (capability-driven).
- Verified in sim (single skew, 2-channel batch, peaking, preset, silent-
  device inference, offline failure) — **not live**: both MTPX units are
  powered off (probe of .15 → offline, as expected). 36 tests pass.

## 2026-07-10 — DEPLOYED TO THE NAS (M4 residency, first half)

Nexus Core runs headless in Docker on the NAS at **nas.joe.bot:8675**
(10.0.0.2, aarch64, host networking, `restart: unless-stopped`, healthy).
Verified from the Mac: health via IP and domain, then NAS-resident probes of
the live rack — MGP online 12 ms, **SMX online 1 ms**. Registry + event log
persist in `/volume1/docker/nexus-core/data/`. Deploy recipe (tar-over-ssh —
the NAS rsync is restricted) is in NEXUS-DEPLOYMENT.md. Remaining M4 half:
persistent connection pooling + unsolicited-response listening.

## v0.2.0 — M2 first wave

- **Three-client day**: the same MGP was driven via curl, the desktop
  GlitchBoard "Nexus API" connection type, and the ported iPad GlitchBoard
  (preset 52 from the iPad, 2026-07-10 19:58 in the event log) — none of
  them speaking SIS.
- **New adapters**: Matrix 12800 (tie/untie/query per deployed lab code),
  SMX (RprNN presets — the family exception —, plane ties `PP*in*out&/$`),
  DMS 3600 (installed 36×36 ties), and generic **`extron_sis`** so any Extron box can
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
- **Joebot Lab telemetry relay (started locally, not NAS-deployed):** this is
  strictly optional. If `NEXUS_LAB_URL` is configured, Nexus can relay the
  NAS's established port-8080 read-only poller (SMX board/plane inventory,
  input-presence dots, rails, and health) through `/devices/{id}/telemetry`.
  A normal Nexus install has no Lab dependency; its future native telemetry
  scheduler will use the same client contract when Lab is absent.
- **GlitchBoard Show Check (local desktop work, not NAS-deployed):** consumes
  Nexus telemetry only as optional read-only evidence. Its current matrix-route
  preflight distinguishes present / absent / not checked / no sensor and keeps
  the operator's explicit warn-or-skip policy separate from telemetry itself.
- No unsolicited-response listening (needs persistent connections, M4).
- Groups endpoint returns `[]` (shape reserved, lands M2).
- Coordination plane (app registration, intents, scenes, recording) not
  started — later milestone, per the locked plan.
