# Nexus Core — Next

## M2 — More adapters + groups
- ~~Matrix 12800 adapter~~ ✅ v0.2.0 (live fire pending — unit offline)
- ~~SMX adapter with plane ties + RprNN presets~~ ✅ v0.2.0 (probe + tie
  queries live-verified; first live preset recall needs an operator watching)
- ~~DMS 3600 adapter~~ ✅ v0.2.0 (unit offline)
- ~~Generic `extron_sis` registry type + registry reload endpoint~~ ✅ v0.2.0
- **MTPX Plus** adapter: verified forms `W{in}*{r}*{g}*{b}Iseq` (skew),
  `W{out}*{0|1}Opek` (peaking), preset recall `N.`, CRLF-terminated;
  doc-derived ties (`!/&/%/$`), tie reads (`{out}A/B/C`), mutes, `S` status
  as `verified: false` until the units power on. Batch action (all channels,
  one connection) — port of joebot-lab `/api/mtpx/batch` + GlitchBoard
  `sendBatch`. Needs a multi-command write in the transport.
- Logical groups/aliases (`/api/v1/groups` goes real): e.g. `group.wall`
  fans one action to many targets.
- Query-backed state: adapters read skew/ties on probe so state starts
  `query`-sourced, not empty.
- SMX live verification session (operator watching): `Rpr01` recall +
  plane tie + auto-switch cross-check with the lab dashboard.

## M3 — GlitchBoard integration
- New connection type `"Nexus"` in Rig Config: one client file
  (NexusBridge.swift, ~NASBridge-sized) + one dispatcher branch in
  `performArmedSend`. Cues/timeline/arm-gate untouched.
- **Direct transports stay default + fallback. Nexus never required.**
- Measure beat-cue latency through Nexus vs direct before trusting it live.

## M4 — NAS residency + connection ownership
- Deploy to Synology (docs/NEXUS-DEPLOYMENT.md), set NEXUS_TOKEN.
- Persistent connection pool per device, policy from *measured* behavior
  (MGP: ~310s idle self-close, keepalive resets timer, 4+ concurrent OK);
  gap-aware recycle; unsolicited-response listener → `query`-sourced state.
- Polling where appropriate; `degraded` status semantics.
- Event log rotation/retention (daily / 100MB / 7 days per the vision doc).

## Later
- **IPCP 505 adapter** — relay `{r}*{0|1|2}O` + Flex DO are already proven
  from GlitchBoard; IR needs the EIR scan on the live unit first
  (`ESC LF CR` file listing, then function browse 1–126).
- **Coordination plane** — app registration, heartbeats, intents, scenes,
  session recording/packaging for Glitch Catalog, operating modes
  (Autonomous/Sync/Managed) from the March vision doc.
- **Nexus Control** admin app (SwiftUI) — the API already carries what it
  needs: capabilities, probe, guarded raw terminal, events.
- **Bridge agents** — USB/serial/MIDI devices attached to a Mac or Pi
  register and advertise capabilities (DirtyMixer stays the canonical
  exception: Nexus → DirtyMixerApp → USB).
- Preset/input **name queries** (`{n}*Nmp` etc.) so no UI ever shows
  "Input 3" when "VHS Deck 1" exists.
