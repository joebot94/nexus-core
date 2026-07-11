# Nexus Core — Status (honest ledger)

_Updated: 2026-07-11 (v0.3.0 + bounded hardware-name reads)_

## 2026-07-11 — hardware-stored names, without the giant sweep

- **Read-only bounded name banks:** `GET /api/v1/devices/{id}/names` accepts
  `kind=input|output|preset`, `start`, and `count` (1–32). Matrix 12800 and
  DMS 3600 expose input/output/preset labels; SMX deliberately exposes
  input/output labels only until preset-label readback is bench-confirmed.
- **Profile-bound:** a 24×24 configured DMS cannot be asked for input 32;
  requests outside the installed hardware profile are rejected instead of
  inventing a maximum chassis.
- **One connection per bank:** TCP `exchange_sequence` authenticates once,
  then pairs each query reply to its channel. This avoids a 32-connection
  burst and prevents GlitchBoard from ever performing an accidental full
  12800 name sweep.
- **Truth labeling:** the action is `verified=false` until its exact live
  response format has been supervised on hardware. Simulated endpoint and
  boundary coverage pass; no NAS deployment or rack command was made for this
  slice.

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
- **Hardware names (local desktop + Nexus work, not NAS-deployed):** Show
  Check can explicitly sync the first input name bank and show those labels
  beside its route sources. Output/preset pickers and scroll-driven banks are
  the next UI slice. Matrix/DMS name commands are based on the existing Lab
  control code; their live response parsing still needs supervised validation.
- No unsolicited-response listening (needs persistent connections, M4).
- Groups endpoint returns `[]` (shape reserved, lands M2).
- Coordination plane (app registration, intents, scenes, recording) not
  started — later milestone, per the locked plan.

## v0.5.0 (2026-07-11, local — NAS still runs v0.4.0)

- **Wall cascade planner** (`nexus/wallplan.py` + `docs/MTPX-WALL-DESIGN.md`):
  the "figure it out once" logic for the 5×MTPX-128 / 16-slot wall — port
  budgets, loopback patch lists, per-unit tie sets, 12800 identity baseline,
  skew distribution across passes. Pure planning; fires nothing; 9 tests.
- **MTPX `save_preset`** (`{N},`) added, `verified=false` like `tie` — the
  full ties→save→recall loop now exists in the API but the whole chain waits
  on the design doc's §7 bench pass before anything fires at hardware.

## v0.6.0 (2026-07-11, local — NAS still runs v0.4.0)

- **Connection pooling (M4)** — `transports/pool.py`, a drop-in for the
  one-shot transport. One held socket per device: single reader task routes
  bytes to the in-flight exchange or, when idle, to an unsolicited-line
  listener. Gap-aware recycle at 280s idle (under the MGP's measured ~310s
  self-close), transparent retry-once when the socket dies mid-send (the
  self-close race), opt-in keepalive that never dials a dark device.
  Silence stays a non-failure (MTPX no-response semantics preserved).
- **Unsolicited → state**: `adapter.parse_unsolicited(line)` (family +
  MGP/MTPX overrides, deliberately conservative) feeds the state store as
  query-sourced values and emits `unsolicited` events on the WS stream.
  Front-panel changes become visible to every client — once live-verified.
- Registry: per-device `connection: pooled` + `idle_recycle_s`/`keepalive_s`;
  default mgp.1 entry is pooled w/ 240s keepalive. `/registry/reload` now
  closes outgoing pooled sockets and rewires listeners.
- 68 tests. **Not yet live-fired**: pooled path against the real MGP (held-
  socket latency, race handling, what it actually volunteers unsolicited)
  needs the operator session. NAS registry needs the `connection` field
  hot-edited (or registry reset) when v0.6.0 deploys.

## v0.7.0 (2026-07-11, local — NAS still runs v0.4.0)

- **Make-before-break socket rotation** (opt-in `rotate_after_s`): as the live
  socket ages past the threshold, the pool opens a fresh standby ALONGSIDE it
  in the background and swaps only once the standby is ready — sends keep
  flowing on the current socket the whole time, so the hot path never waits on
  a connect and no send races a device that closes on total session lifetime
  (not just idle). Age is time-since-connect, complementing keepalive (idle).
  The reactive recycle + retry-once path stays underneath as the safety net.
  Only the live primary's reader routes unsolicited lines, so the brief
  two-socket overlap never double-counts a broadcast. `rotations` stat added;
  registry gains per-device `rotate_after_s` (default 0 = off). 3 new tests,
  71 total. Off by default on the MGP (its idle self-close is already covered
  by keepalive); enable per-device for gear that closes on session age.

## v0.8.0 (2026-07-11, local — NAS still runs v0.4.0)

- **Groups + scenes** (`nexus/scenes.py`, the coordination plane's first real
  slice). A **group** is a named alias for device targets; `POST
  /groups/{id}/actions` fans one action to every member. A **scene** is a
  named, ordered list of steps (each targeting a device OR a group) run in
  order through the same adapter path a single action uses — the "normal"
  baseline is `scene.baseline`, chaos modes become delta scenes.
- `GET /groups`, `GET /scenes`, `POST /groups/{id}/actions`,
  `POST /scenes/{id}/recall` (+ `?dry_run=true` resolves/validates without
  firing), `POST /scenes/reload`. Persisted in `data/jbt/scenes.jbt`,
  hand-editable + reloadable like the device registry; malformed entries skip
  with a warning.
- `/actions`, group fan-out, and scene recall all share one `_run_action`
  helper so status-marking, state updates, and event logging are identical.
- 11 new tests (store + API over sim devices); 82 total. Baseline scene
  currently only carries the MGP clean-layout step; the MTPX/matrix/SMX steps
  get authored (or WallPlan-generated) once they clear the bench pass.

## v0.9.0 (2026-07-11, local — NAS still runs v0.4.0)

- **Registry wall placement + `/wall/plan`** — MTPX devices now carry
  `wall_slots` / `wall_passes` / `wall_model` in the registry, so wall
  placement lives in one source of truth. `wallplan.plan_from_registry()`
  turns that into a WallPlan, and `GET /wall/plan` returns the resolved lanes,
  physical loopback patch list, baseline tie sets, Matrix identity routing,
  and MGP assignment — read-only planning truth for a future graphical wall
  view and for racking the cables. Default registry ships example placement on
  the two MTPX units (2×2). 3 new tests; 85 total.

## v0.10.0 (2026-07-11, local — NAS still runs v0.4.0)

- **Parallel lane pool** (`transports/lanes.py`, ported from Joe's MTPXControl
  `MTPXNetworkService`). The MTPX fires a big skew burst fastest across several
  concurrent sockets, not one serialized socket. `LanePoolTransport` opens N
  lanes (default 10, ≤32), and `exchange_batch` round-robins the commands into
  one chunk per lane and writes them **concurrently** (`asyncio.gather`) — a
  burst of M commands leaves in ~M/N serial writes. Fire-and-forget: a
  completed write is success (MTPX no-response mode), echoes drained
  best-effort, dead lanes dropped mid-burst.
- Interface-compatible, so **no adapter change** — the MTPX adapter's existing
  `exchange_batch` skew path fans across lanes automatically when the device's
  registry `connection` is `"lanes"`. Registry: `connection: "lanes"` +
  `lane_count`; both default MTPX units now use 10 lanes. MGP keeps its single
  pooled socket (right for a stateful device with front-panel feedback).
- 7 new tests against a multi-connection sim that proves the fan-out (peak
  concurrent sockets, per-lane command spread, silent-burst success); 92 total.
  Live lane-count tuning is a bench item — 10 is Joe's MTPXControl figure.

## v0.11.0 (2026-07-11, local — NAS still runs v0.4.0)

- **Baseline scene generated from the wall plan** — `POST /wall/baseline-scene`
  builds the "normal" baseline (per-lane MTPX ties + skew-0, Matrix identity
  routing, MGP clean layout) straight from registry wall placement and saves it
  as `scene.wall-baseline`. Ties the session together: wall planner (v0.5/0.9)
  + scenes (v0.8) + lanes (v0.10) converge into one recallable, inspectable
  baseline. MTPX tie/skew steps are verified=false so live recall stays
  bench-gated; dry-run (`/scenes/{id}/recall?dry_run=true`) is always safe.
  2 new tests; 95 total.
