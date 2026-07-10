# Nexus — Grand Server Architecture
> Joebot Ecosystem Central Coordinator
> GitHub: github.com/joebot94/nexus
> Document version 1.3 — March 2026
> Changes: Added always-on event logger, session packaging endpoint, client operating modes
> (Autonomous/Sync/Managed), layout query system, Glitch Catalog dual recording modes,
> .jbt mandate, port corrections throughout, TextWall and Lyric App added to app roles.
> 🦖 Joebot Ecosystem

---

## The One Sentence Version

**Apps speak Nexus. Nexus speaks hardware. Users see magic.** 🦖

---

## The Absolute Rules — Never Change

1. Every app talks to Nexus via WebSocket — always
2. Nexus owns ALL hardware adapters — Extron TCP/SIS, IPCP HTTP
3. DirtyMixerApp is the ONE exception — owns USB serial to dirty mixer board directly
4. Apps are UIs only — no hardware knowledge except DirtyMixerApp
5. Nexus port is **8675** — not 8765. 8675. Like 867-5309. 🦖📞
6. Every file is .jbt — no plain .json config files anywhere

---

## The Final Architecture — Locked

```
┌─────────────────────────────────────────────────────────┐
│                      NEXUS                              │
│              (Python asyncio server)                    │
│              Port 8675 — Jenny 📞                      │
│                                                         │
│  Hardware Adapters:                                     │
│  MTPXAdapter     → mtpx1.extron.video:23               │
│  MGPAdapter      → mgp1.extron.video:23                │
│  DMSAdapter      → dms.extron.video:23                 │
│  MatrixAdapter   → mx.extron.video:23                  │
│  IPCPAdapter     → ipcp505-1.extron.video (HTTP)       │
│  IPLAdapter      → iplt-s4.extron.video:23             │
│  VSCAdapter      → via IPCP serial passthrough         │
│  DirtyMixerAdap  → via DirtyMixerApp (see exception)  │
│                                                         │
│  Core Services:                                         │
│  EventLogger     → ~/.nexus/logs/nexus_rolling.jbt     │
│  StateStore      → in-memory + ~/.nexus/state/         │
│  AdapterManager  → manages all hardware connections    │
└─────────────────────────────────────────────────────────┘
         ↑↓         ↑↓        ↑↓       ↑↓        ↑↓
    GlitchBoard   Atlas  DirtyMixer  Glitch   Observatory
    (timeline)   (Extron  (Mixer    Catalog   (monitor)
                  UI)      UI)      (archive)
         ↑↓                  ↑↓
     TextWall            LyricApp
     (display)           (author)
```

**Every app is a UI client. Nexus handles all hardware.**

---

## App Roles

| App | Role | Hardware Access |
|---|---|---|
| GlitchBoard | Timeline/DAW show control UI | None — sends intents to Nexus |
| Atlas | Extron gear control UI | None — sends intents to Nexus |
| DirtyMixerApp | Mixer control UI + board owner | USB Serial to board only (see exception) |
| Glitch Catalog | Session archive UI | None — sends intents to Nexus |
| Observatory | Monitor and launcher UI | None — read only from Nexus |
| TextWall | Text/lyric display UI | None — receives commands from Nexus |
| Lyric App | Lyric authoring UI | None — sends intents to Nexus |
| Nexus Control | Device admin UI | None — sends intents to Nexus |
| MIDI App | Controller mapping UI | None — sends intents to Nexus |

---

## The DirtyMixerApp Exception

DirtyMixerApp is the one exception to the rule.

DirtyMixerApp communicates directly with the physical dirty mixer board over USB serial because:
- The dirty mixer board is a custom built device
- It connects via USB-C to the host Mac
- USB serial is inherently local and direct
- DirtyMixerApp is the designated owner of that hardware

**However** — DirtyMixerApp still participates in Nexus fully:
- Registers with Nexus on launch
- Reports board state to Nexus constantly
- Receives commands FROM Nexus when other apps want to change something
- When GlitchBoard wants the mixer to do something: Nexus → DirtyMixerApp → USB → Board

**The dirty mixer flow:**
```
GlitchBoard → Nexus → DirtyMixerApp → USB Serial → Board
```

**DirtyMixerApp reporting state:**
```
Board state changes → DirtyMixerApp → Nexus state store → all apps notified
```

---

## Client Operating Modes

Every app that connects to Nexus operates in one of three modes.
The mode controls whether the app obeys incoming commands.
**State reporting to Nexus is always on regardless of mode.**

```
┌─ Client Operating Mode ──────────────────────────────────┐
│                                                          │
│  ● Autonomous  — app does its own thing                 │
│                  reports state to Nexus                  │
│                  ignores incoming commands               │
│                  "fuck off mode"                         │
│                                                          │
│  ● Sync        — app watches other apps via Nexus        │
│                  reacts intelligently to their state     │
│                  nobody commanded it — it chose to follow│
│                  configurable: Follow / Invert / Offset  │
│                                                          │
│  ● Managed     — full Nexus control                     │
│                  all incoming commands obeyed            │
│                  default performance mode                │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### Sync Mode — Follow / Invert / Offset

When an app is in Sync mode it can follow another app's state in different ways:

**Follow** — mirror the source app's configuration exactly.
TextWall in X pattern → synced app also uses X pattern.

**Invert** — use the opposite of the source app's active cells.
TextWall active cells → synced app activates all OTHER cells.
Video glitches where text isn't. Text fills where video isn't.

**Offset** — shift the source pattern by N cells or beats.

Example — TextWall and WallGlitch synchronized:
```
TextWall active cells:      WallGlitch FOLLOW:
┌──┬──┬──┐                  ┌──┬──┬──┐
│TX│  │TX│                  │🎬│  │🎬│
├──┼──┼──┤                  ├──┼──┼──┤
│  │TX│  │                  │  │🎬│  │
├──┼──┼──┤                  ├──┼──┼──┤
│TX│  │TX│                  │🎬│  │🎬│
└──┴──┴──┘                  └──┴──┴──┘

WallGlitch INVERT:
┌──┬──┬──┐
│  │🎬│  │
├──┼──┼──┤
│🎬│  │🎬│
├──┼──┼──┤
│  │🎬│  │
└──┴──┴──┘
```

### Operating Mode Registration

Apps declare their default mode on registration and can change it at runtime:

```json
{
  "type": "register",
  "payload": {
    "client_id": "textwall_v1",
    "client_type": "display",
    "operating_mode": "managed",
    "sync_source": null,
    "sync_behavior": null
  }
}
```

Change mode at runtime:
```json
{
  "type": "set_operating_mode",
  "payload": {
    "client_id": "wallglitch_v1",
    "mode": "sync",
    "sync_source": "textwall_v1",
    "sync_behavior": "invert"
  }
}
```

Observatory shows each app's current operating mode as a badge on its card.

---

## Layout Query System

Any app can ask Nexus for another app's current grid/layout state.
This is how Atlas knows what TextWall is doing without TextWall knowing about Atlas.

```json
{
  "type": "query",
  "payload": {
    "target_client_id": "textwall_v1",
    "fields": ["grid_size", "layout", "active_cells", "mode"]
  }
}
```

Nexus returns last known state from state store:
```json
{
  "type": "query_response",
  "payload": {
    "client_id": "textwall_v1",
    "grid_size": "3x3",
    "layout": "x_pattern",
    "active_cells": [0,2,4,6,8],
    "mode": "word"
  }
}
```

Atlas receives this and can fire MGP presets to match the TextWall cell configuration.
No direct communication between Atlas and TextWall. Nexus is the shared brain.

---

## Always-On Event Logger

Nexus logs every message that passes through it to a rolling .jbt file.
This runs continuously in the background — no app needs to think about recording.

```
nexus/core/event_logger.py

Rolling log: ~/.nexus/logs/nexus_rolling.jbt
- Every message logged with timestamp, source, target, type, payload
- Session markers embedded when Glitch Catalog says start/stop
- Auto-rotates daily or at 100MB
- Last 7 days retained by default
```

### Log Entry Format

```json
{
  "jbt_type": "nexus_event_log",
  "version": "1.0",
  "payload": {
    "events": [
      {
        "timestamp": "2026-03-15T04:17:32.667Z",
        "relative_ms": 1234,
        "type": "state_update",
        "source": "dirtymixer_v1",
        "target": "nexus",
        "summary": "CH3 mix changed to 194",
        "payload": {
          "channels": [
            {"id": 3, "mix": 194}
          ]
        }
      },
      {
        "timestamp": "2026-03-15T04:17:33.100Z",
        "relative_ms": 1667,
        "type": "session_marker",
        "source": "glitch_catalog",
        "summary": "Session start — Basement Burn-In"
      }
    ]
  }
}
```

The `summary` field is human readable plain English — what happened, not raw JSON.
This is what Glitch Catalog displays in the timeline event stream.

### Session Packaging Endpoint

When Glitch Catalog sends `session_stop`, Nexus packages everything between
the start and stop markers into a single `glitch_session.jbt` and sends it back.

```
Glitch Catalog → session_start → Nexus embeds marker in rolling log
                                        ↓
                              [entire session recorded automatically]
                                        ↓
Glitch Catalog → session_stop  → Nexus slices log between markers
                               → packages as glitch_session.jbt
                               → sends file to Glitch Catalog
                               → Glitch Catalog saves and opens in replay viewer
```

Glitch Catalog does not need to subscribe to anything for recording purposes.
Just start, stop, receive file.

---

## Glitch Catalog Recording Modes

Two modes available — user's choice per session:

```
┌─ Recording Source ──────────────────────────────────┐
│                                                     │
│  ● Nexus log (recommended)                         │
│    Full ecosystem recording                        │
│    Every device, every app, everything Nexus sees  │
│    Zero extra network traffic                      │
│                                                     │
│  ○ Self-record                                     │
│    Glitch Catalog subscribes directly              │
│    Works standalone without Nexus logging          │
│    Good for lightweight setups                     │
│                                                     │
│  Auto-fallback: if Nexus log unavailable,          │
│  automatically switches to self-record             │
│  Session is never lost due to disconnection        │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Auto-fallback is critical** — if Nexus goes down mid-session,
Glitch Catalog switches to self-record automatically so nothing is lost.

---

## .jbt Mandate

**Every file in the Joebot ecosystem is .jbt. No exceptions.**

JSON is the encoding format under the hood. .jbt is the contract on top.
The `jbt_type` field tells every app what it's looking at.

```
Device registry:      ~/.nexus/jbt/device_registry.jbt
EIR libraries:        ~/.nexus/jbt/eir_library_{device_id}.jbt
Capabilities cache:   ~/JBT/glitchboard/capabilities_cache.jbt
App preferences:      ~/JBT/{app}/prefs.jbt
Scenes:               ~/.nexus/jbt/scenes/
Patterns:             ~/.nexus/jbt/patterns/
Rolling event log:    ~/.nexus/logs/nexus_rolling.jbt
```

**Migrate away from:**
```
config/devices.json       → ~/.nexus/jbt/device_registry.jbt
capabilities_cache.json   → capabilities_cache.jbt
Any other .json files     → .jbt equivalents
```

---

## What Nexus Does

Nexus is the only thing with hardware knowledge. It has an adapter for every device type.

**Nexus responsibilities:**
- Accept WebSocket connections from all apps
- Route messages between apps
- Maintain state store for every connected client
- Hold last known state when a client goes offline
- Alert Observatory when a client drops unexpectedly
- Handle .jbt scene snapshots — poll all clients and adapters, bundle state
- Provide a queryable API so any client can ask "what is X doing right now"
- Own and execute ALL hardware adapters (except dirty mixer — see exception)
- Listen for unsolicited hardware responses and update state accordingly
- Log ALL events continuously to rolling .jbt log file
- Package session logs on demand for Glitch Catalog
- Track and enforce client operating modes
- Respond to layout queries from any app

---

## Hardware Ownership

| Hardware | Owner | Protocol |
|---|---|---|
| MTPX Plus series | Nexus MTPXAdapter | Extron SIS TCP port 23 |
| MGP 464 | Nexus MGPAdapter | Extron SIS TCP port 23 |
| DMS 3600 | Nexus DMSAdapter | Extron SIS TCP port 23 |
| Matrix 12800 | Nexus MatrixAdapter | Extron SIS TCP port 23 |
| IPCP 505 | Nexus IPCPAdapter | HTTP + Extron SIS |
| IPL T series | Nexus IPLAdapter | HTTP + Extron SIS |
| VSC series | Nexus VSCAdapter | Via IPCP serial passthrough 9600 8N1 |
| DSC 401A | Nexus DSCAdapter | Extron SIS TCP port 23 |
| Dirty Mixer Board | DirtyMixerApp | USB Serial (exception) |

---

## Action Flow Examples

**GlitchBoard wants MTPX blue skew at maximum:**
```
GlitchBoard sends intent to Nexus:
  action: set_input_skew
  device: device.mtpx.1
  params: {input: 3, red: 0, green: 0, blue: 31}

Nexus MTPXAdapter translates:
  3*0*0*31*4Iseq↵

Nexus sends to mtpx1.extron.video:23
Hardware responds
Nexus updates state store
EventLogger records with human readable summary
All apps notified of new state
```

**GlitchBoard fires TextWall lyric cue:**
```
GlitchBoard sends TWO messages simultaneously:

1. lyric_update → TextWall:
   text: "welcome to the machine"

2. textwall_config → TextWall:
   grid_size: "2x2"
   layout: "all_cells"
   mode: "word"

TextWall switches layout AND displays text simultaneously.
EventLogger records both.
```

**Atlas queries TextWall layout to match MGP config:**
```
Atlas sends layout query to Nexus:
  target: textwall_v1
  fields: [grid_size, layout, active_cells]

Nexus returns last known TextWall state.
Atlas fires MGP presets to match cell configuration.
No direct Atlas ↔ TextWall communication.
```

**IPCP relay pulse on beat:**
```
GlitchBoard sends intent to Nexus:
  action: pulse_relay
  device: device.ipcp505.1
  params: {relay: 1}

Nexus IPCPAdapter fires:
  GET http://ipcp505-1.extron.video/W=1R01

Relay clicks on front panel
EventLogger records: "IPCP 505 #1 relay 1 pulsed"
```

---

## Unsolicited Hardware Responses

When a user turns a knob on the front panel of an Extron device the device sends
an unsolicited response back over TCP. Nexus adapters listen continuously.

Example: User turns MTPX horizontal skew knob manually
```
MTPX sends: Iseq03•00•00•15↵  (unprompted)
Nexus MTPXAdapter receives and parses it
Nexus updates state store for device.mtpx.1
EventLogger records: "MTPX Plus #1 input 3 blue skew changed to 15 (front panel)"
All apps notified — Atlas UI updates to show new value
Glitch Catalog timeline shows the change
```

---

## Capability Discovery

Nexus exposes device capabilities so apps can build dynamic UIs.

When GlitchBoard asks "what can the MTPX do":
```json
{
  "type": "capabilities.query",
  "payload": { "target_client_id": "device.mtpx.1" }
}
```

Nexus responds from adapter knowledge:
```json
{
  "capabilities": {
    "actions": [
      {
        "action": "set_input_skew",
        "params": {
          "input": {"type": "int", "range": [1,16]},
          "red":   {"type": "int", "range": [0,31]},
          "green": {"type": "int", "range": [0,31]},
          "blue":  {"type": "int", "range": [0,31]}
        }
      }
    ]
  }
}
```

When GlitchBoard asks "what can TextWall do":
```json
{
  "capabilities": {
    "grid_sizes": ["1x1","2x2","3x3","4x4","8x8","16x16","custom"],
    "modes": ["line","word","letter","scatter","reveal","checkerboard_scatter"],
    "max_hz": 20,
    "max_instances": 32,
    "layouts": ["all","x_pattern","center","corners","top_row","bottom_row",
                "center_row","border","star_5x5","star_7x7","custom"],
    "saved_layouts": ["verse_center_row","chorus_corners","scatter_full"]
  }
}
```

GlitchBoard builds its cue editors from these responses. No hardcoding anywhere.

---

## Naming System

Wherever a name exists it must be shown. Nexus queries names on connect
and stores them in state. Every app gets names via capability discovery.

```
Input names      → shown in tooltips, dropdowns, cue editors
Output names     → shown in tooltips, dropdowns, cue editors
Preset names     → shown in tooltips, dropdowns, cue editors
IR command names → shown in dropdowns (from EIR auto-discovery)
Device labels    → shown everywhere
Scene names      → shown everywhere
Layout names     → shown in TextWall and GlitchBoard pickers
```

No app ever shows "Input 3" when "VHS Deck 1" is available.
No app ever shows "File 0 Command 13" when "Blue" is available.

---

## Connection Model

### Client Registration

```json
{
  "type": "register",
  "client_id": "textwall_v1",
  "client_type": "display",
  "version": "1.0.0",
  "operating_mode": "managed",
  "capabilities": ["word_mode","scatter_mode","reveal_mode","16x16"]
}
```

### Heartbeat

Every client sends heartbeat every 5 seconds.
Miss 3 = marked offline. Last known state retained.

### State Reporting

Clients report state whenever something changes.
Nexus stores it. EventLogger records it. Anyone can query it.
**State reporting is always on regardless of operating mode.**

---

## Nexus Server Structure

```
nexus/
├── main.py                   🦖 startup log required
├── requirements.txt
├── README.md
├── config/
│   └── settings.py           NEXUS_PORT = 8675
├── core/
│   ├── registry.py
│   ├── state_store.py
│   ├── heartbeat.py
│   ├── log_bus.py
│   ├── event_logger.py       ← NEW — always-on rolling log
│   ├── session_packager.py   ← NEW — packages log slices for Glitch Catalog
│   ├── operating_modes.py    ← NEW — autonomous/sync/managed logic
│   ├── dispatcher.py
│   └── adapter_manager.py
├── api/
│   ├── models.py
│   ├── websocket_server.py
│   └── handlers.py
├── adapters/
│   ├── base.py
│   ├── extron_common.py      ← shared SIS helpers, universal commands
│   ├── mtpx_adapter.py       ← skew, peaking, routing
│   ├── mgp_adapter.py        ← preset recall with/without input, mute
│   ├── dms_adapter.py        ← preset recall, mute
│   ├── matrix_adapter.py     ← routing, presets
│   ├── ipcp_adapter.py       ← relay, IR, serial passthrough, EIR discovery
│   ├── ipl_adapter.py        ← serial passthrough
│   ├── vsc_adapter.py        ← via IPCP serial 9600 8N1
│   └── dirtymixer_adapter.py ← routes to DirtyMixerApp (exception)
├── jbt/
│   ├── parser.py
│   └── writer.py
└── tools/
    └── lyric_player.py       ← deadline tool — fires timed lyrics to Nexus
```

---

## Device Registry

Stored at: `~/.nexus/jbt/device_registry.jbt` (type: `nexus_device_registry`)
No more `devices.json` — .jbt only.

| Device ID | Label | Adapter | Hostname | Port |
|---|---|---|---|---|
| `device.mtpx.1` | MTPX Plus 1616 | MTPXAdapter | mtpx1.extron.video | 23 |
| `device.mtpx.2` | MTPX Plus 168 | MTPXAdapter | mtpx2.extron.video | 23 |
| `device.mgp.1` | MGP 464 #1 | MGPAdapter | mgp1.extron.video | 23 |
| `device.mgp.2` | MGP 464 #2 | MGPAdapter | mgp2.extron.video | 23 |
| `device.mgp.3` | MGP 464 #3 | MGPAdapter | mgp3.extron.video | 23 |
| `device.dms.main` | DMS 3600 | DMSAdapter | dms.extron.video | 23 |
| `device.matrix.main` | Matrix 12800 | MatrixAdapter | mx.extron.video | 23 |
| `device.ipcp505.1` | IPCP 505 #1 | IPCPAdapter | ipcp505-1.extron.video | HTTP |
| `device.ipcp505.2` | IPCP 505 #2 | IPCPAdapter | ipcp505-2.extron.video | HTTP |
| `device.ipcp505.3` | IPCP 505 #3 | IPCPAdapter | ipcp505-3.extron.video | HTTP |
| `device.dirtymixer.1` | Dirty Mixer Board | DirtyMixerAdapter* | via DirtyMixerApp | USB |

*DirtyMixerAdapter routes through DirtyMixerApp — does not connect to hardware directly.

---

## Configuration

```python
NEXUS_HOST = "0.0.0.0"
NEXUS_PORT = 8675              # Jenny 📞 — not 8765, not 8675+1, exactly 8675
HEARTBEAT_INTERVAL = 5         # seconds
HEARTBEAT_TIMEOUT = 3          # missed beats before offline
STATE_STORE_PATH = "~/.nexus/state/"
JBT_LIBRARY_PATH = "~/.nexus/jbt/"
LOG_PATH = "~/.nexus/logs/"
LOG_ROTATE_MB = 100
LOG_RETAIN_DAYS = 7
MASTER_HOSTNAME = "show.joe.bot"
```

---

## Deployment Options

### Single Machine (typical)
- Nexus runs as background service on same Mac as all apps
- Apps connect to localhost:8675
- User never interacts with Nexus directly

### Dedicated Server (studio setup)
- Nexus runs on N100 mini PC or Mac Mini
- Apps connect over local network to nexus.joe.bot:8675
- Always on, headless, silent

---

## Related Documents

- `JBT_Format_Spec.md` — shared file format
- `Extron_SIS_Reference.md` — device command reference
- `DirtyMixerApp_BuildGuide.md` — dirty mixer app spec
- `Observatory_BuildGuide.md` — Observatory spec
- `GlitchBoard_Spec.md` — GlitchBoard DAW spec
- `TextWall_BuildGuide.md` — TextWall display app spec
- `LyricApp_BuildGuide.md` — Lyric App authoring spec
- `NexusControl_BuildGuide.md` — device admin app spec

---

*Nexus — Central coordinator for the Joebot studio ecosystem*
*Apps speak Nexus. Nexus speaks hardware. Users see magic.* 🦖
*github.com/joebot94/nexus*
*Document version 1.3 — March 2026*
