# Nexus Core — Architecture

> Successor to the March 2026 `Nexus_Architecture.md` v1.3 (kept in
> `docs/reference/`). The one-sentence version is unchanged:
> **Apps speak Nexus. Nexus speaks hardware.** What changed: the primary
> client contract is now versioned REST + WebSocket instead of a bespoke
> WS envelope, and the service is built device-plane-first.

## Lineage — how this repo relates to what came before

| Prior work | What it was | What Nexus Core takes from it |
|---|---|---|
| `joebot-ecosystem/nexus` (Python) | App-to-app WebSocket bus — registration, heartbeats, intents, scenes, session recording. **Zero device control** (adapters were explicitly deferred in the original build prompt). | Registry/event-log/scene *concepts*; the coordination plane returns in a later milestone. |
| `joebot-lab` (NAS dashboard) | The real device-control prototype: proven SIS transports, polling, MTPX batch API, IPCP passthrough tricks. | Protocol knowledge, re-homed into adapters as they're built (M2+). The dashboard keeps running untouched and becomes a Nexus client later. |
| GlitchBoard v0.9–v0.22 | Live-verified wire behavior: MGP `2*NN.`, MTPX `W…Iseq`, CR/CRLF framing, banner format, ~310s idle timeout. | The transport semantics and the verified command sets. |

**Protocol truth hierarchy:** live-verified July 2026 code → deployed
joebot-lab code → March 2026 docs. Doc-only commands ship with
`verified: false` in their ActionSpec until bench-tested.

## Two planes

1. **Device plane (v1, this repo now)** — device registry, adapters,
   normalized actions, state, events. The hardware abstraction.
2. **Coordination plane (later milestone)** — app registration, intents
   between apps, scenes, session recording for Glitch Catalog, operating
   modes (Autonomous/Sync/Managed). Layers onto the same EventBus/WS.

## Component map

```
nexus/
├── config.py         env-driven Settings (port 8675, data dir, token, simulate)
├── jbt.py            .jbt envelope read/write (the mandate: no plain .json)
├── registry.py       device_registry.jbt → DeviceEntry{config, adapter, status}
├── state.py          last-known state, every value stamped {source, updated_at}
├── events.py         ring buffer + WS fan-out + rolling nexus_event_log.jbt
├── transports/tcp.py one-shot SIS exchange (port of verified TCPTransport.swift)
├── adapters/
│   ├── base.py       DeviceAdapter + ActionSpec{params, destructive, verified}
│   ├── extron_sis.py family base: universal `N.` recall, E01–E28 table, probe via Q
│   └── mgp.py        MGP 464: `2*NN.` recall, window routing, + Simulator
└── api/              REST /api/v1 + WebSocket /api/v1/ws
```

## Adapter model

An adapter declares its actions (`ActionSpec`: params schema, destructive
flag, verified flag), translates each to wire protocol, parses replies, and
reports **confirmed** state changes. Shared behavior lives in family bases —
`ExtronSISAdapter` implements what the SIS reference calls universal patterns
(preset recall `N.`, bare-letter queries, the shared error table), and model
subclasses override only what differs (MGP layout presets are `2*NN.`).
Adding a device that shares a family = a small subclass + a registry entry.

Every adapter ships a `Simulator` so simulation mode exercises the identical
adapter/API path with only the transport swapped.

## State model

State is never updated because a command was *sent* — only from a parsed
acknowledgment (`command_ack`), an explicit `query`, a `probe`, an
`inferred` deduction, or a `manual` override; each value carries its source
and timestamp. Device status is `unknown / online / offline / degraded`;
an E-code error still proves the device answered (stays online), only
transport silence marks it offline.

## Safety rules

- Destructive commands (device resets `ZG/ZXXX/Z000`, `Esc zXXX`) are never
  exposed as normal actions; when they arrive they'll require an explicit
  confirm flag and be barred from automation. **None exist in v1.**
- The raw command endpoint requires `confirm_raw: true`, is loudly logged,
  and is for diagnostics only (future Nexus Control SIS terminal).
- Clients keep their own arm gates (GlitchBoard's triple gate stays);
  Nexus enforces its own rules independently. Defense in depth.
- **Nexus is never required to run a show** — GlitchBoard keeps direct
  transports as default/fallback. Hard rule from Joe.

## Connections (v1 → M4)

v1 uses one-shot connect-per-command (~40–70 ms against the live MGP,
verified fine for current use). M4 replaces this with persistent pooled
connections driven by *measured* per-device socket behavior — the MGP
self-closes at ~310s idle, tolerates 4+ concurrent sessions, and any
activity resets its timer. Long-term, Nexus should be the sole owner of
device connections (the lab dashboard poller and GlitchBoard-direct are
transitional co-owners).
