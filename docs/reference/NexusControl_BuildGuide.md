# Nexus Control — Build Guide
> Joebot Ecosystem Device Configuration and Administration App
> GitHub: github.com/joebot94/nexus-control
> Document version 1.1 — March 2026
> Changes: Added MIDI configuration tab with APC Mini Mk2 virtual layout and RGB
> button color picker, added operating mode display per connected app, added
> per-device name editing (inputs/outputs/presets), added VSC baud rate config.
> 🦖 Joebot Ecosystem

---

## What Nexus Control Is

Nexus Control is the native macOS SwiftUI administration app for the Joebot Ecosystem.
It is the single place where you configure devices, test connections, browse capabilities,
send raw SIS commands, manage the device registry, and configure MIDI controllers.

It is the "under the hood" app. You use it to set up the ecosystem, test hardware,
and debug problems. During a live performance you probably don't need it open.

---

## Core Philosophy

- **Configuration lives in .jbt files** — device registry, EIR libraries, MIDI mappings, all .jbt
- **Test everything** — every device has a one-click connection test and quick action buttons
- **SIS terminal** — raw command access to any device for debugging and discovery
- **Capability browser** — see exactly what Nexus knows about each device
- **Name everything** — inputs, outputs, presets, IR commands all get human readable names
- **MIDI here** — one place for all controller mappings, all apps benefit
- **Nexus client** — connects to Nexus, shows up in Observatory

---

## Layout

```
┌─ Nexus Control ─────────────────────────────────────────────┐
│  NEXUS CONTROL                              🟢 Nexus  ⚙️    │
│  Device Administration                                       │
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│  Devices     │  [ Devices | Apps | MIDI | Registry ]       │
│  ─────────   │                                              │
│  🟢 IPCP #1  │  ┌─ 🟢 IPCP 505 #1 ───────────────────────┐ │
│  🟢 MTPX #1  │  │  ipcp505-1.extron.video  •  Rack 1     │ │
│  🟢 MTPX #2  │  │  Relays: 8  IR Ports: 8  EIR Files: 2 │ │
│  🔴 MGP #1   │  │                                        │ │
│  🔴 MGP #2   │  │  [ Test ] [ Capabilities ] [ Terminal ]│ │
│  🔴 MGP #3   │  └────────────────────────────────────────┘ │
│  🔴 Matrix   │                                              │
│  🔴 DMS      │  ┌─ 🟢 MTPX Plus #1 ──────────────────────┐ │
│  🔴 IPCP #2  │  │  mtpx1.extron.video  •  Rack 1         │ │
│  🔴 IPCP #3  │  │  16×16 I/O  Firmware: 1.04             │ │
│              │  │                                        │ │
│  [ + Add ]   │  │  [ Test ] [ Capabilities ] [ Terminal ]│ │
│              │  └────────────────────────────────────────┘ │
│  Apps        │                                              │
│  ─────────   │  ┌─ 🔴 MGP 464 #1 ─────────────────────────┐ │
│  🟢 GlitchBd │  │  mgp1.extron.video  •  Rack 2  OFFLINE  │ │
│  🟢 TextWall │  │  Last seen: 2 hours ago                 │ │
│  🔴 Atlas    │  │                                        │ │
│              │  │  [ Test ] [ Edit ] [ Remove ]          │ │
│  Registry    │  └────────────────────────────────────────┘ │
│  ─────────   │                                              │
│  [ Export ]  │                                              │
│  [ Import ]  │                                              │
├──────────────┴──────────────────────────────────────────────┤
│  SIS Terminal  [ MTPX Plus #1 ▼ ]                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ → S↵                                                │   │
│  │ ← +3.28•+4.98•-5.01•+11.52•-12.35•+86.88•03590    │   │
│  │ → 1*0*0*31*4Iseq↵                                  │   │
│  │ ← Iseq01•00•00•31                                  │   │
│  └──────────────────────────────────────────────────────┘   │
│  [ type SIS command here...                    ] [ Send ]   │
└─────────────────────────────────────────────────────────────┘
```

---

## Tab: Devices

Shows all hardware devices from `device_registry.jbt`.
Default tab. Used for hardware setup and testing.

---

## Tab: Apps

Shows all currently connected Nexus clients — software apps, not hardware.

```
┌─ Connected Apps ────────────────────────────────────────────┐
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 🟢 GlitchBoard                                       │  │
│  │ glitchboard_v1  •  daw  •  v1.0.0                   │  │
│  │ Mode: 📡 Managed                                     │  │
│  │ Song: Welcome to the Machine  BPM: 72                │  │
│  │ Cues: 24  Status: Playing                            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 🟢 TextWall                                          │  │
│  │ textwall_v1  •  display  •  v1.0.0                   │  │
│  │ Mode: 📡 Managed  ← [ Change ▼ ]                    │  │
│  │ Grid: 3×3  Layout: center_row  Mode: word            │  │
│  │ Current: "welcome, my son"                           │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 🔴 Atlas                                             │  │
│  │ atlas_v1  •  extron_controller                       │  │
│  │ Last seen: 4 minutes ago                             │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Operating mode badge per app. Change mode from this panel.

---

## Tab: MIDI

All MIDI controller configuration lives here. One place, all apps benefit.
Mappings saved as `midi_mapping.jbt`. All apps get mappings from Nexus.

```
┌─ MIDI Configuration ────────────────────────────────────────┐
│                                                             │
│  Controller: [ APC Mini Mk2 ▼ ]  🟢 Connected             │
│                                                             │
│  ┌─ Virtual Layout ──────────────────────────────────────┐ │
│  │                                                       │ │
│  │  ┌──┬──┬──┬──┬──┬──┬──┬──┐  ← 8×8 button grid       │ │
│  │  │🔵│🔵│  │  │  │  │  │  │  color = idle color       │ │
│  │  ├──┼──┼──┼──┼──┼──┼──┼──┤                           │ │
│  │  │🟠│  │  │  │  │  │  │  │                           │ │
│  │  ├──┼──┼──┼──┼──┼──┼──┼──┤                           │ │
│  │  │  │  │  │  │  │  │  │  │                           │ │
│  │  ├──┼──┼──┼──┼──┼──┼──┼──┤                           │ │
│  │  │  │  │  │  │  │  │  │  │                           │ │
│  │  ├──┼──┼──┼──┼──┼──┼──┼──┤                           │ │
│  │  │  │  │  │  │  │  │  │  │                           │ │
│  │  ├──┼──┼──┼──┼──┼──┼──┼──┤                           │ │
│  │  │  │  │  │  │  │  │  │  │                           │ │
│  │  ├──┼──┼──┼──┼──┼──┼──┼──┤                           │ │
│  │  │  │  │  │  │  │  │  │  │                           │ │
│  │  ├──┼──┼──┼──┼──┼──┼──┼──┤                           │ │
│  │  │  │  │  │  │  │  │  │  │                           │ │
│  │  └──┴──┴──┴──┴──┴──┴──┴──┘                           │ │
│  │  ═══════════════════════════  ← 8 faders              │ │
│  │                                                       │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  Click any button to configure it:                         │
│                                                             │
│  ┌─ Button 1,1 ──────────────────────────────────────┐    │
│  │                                                   │    │
│  │  Idle color:   [ 🔵 #004444 ]  (dim cyan)        │    │
│  │  Active color: [ 💠 #00FFFF ]  (bright cyan)     │    │
│  │                                                   │    │
│  │  Action:  [ recall_preset ▼ ]                    │    │
│  │  Device:  [ DirtyMixer ▼ ]                       │    │
│  │  Preset:  [ 12 — Chaos Mode ]                    │    │
│  │                                                   │    │
│  │  [ Learn Mode ]  [ Test ]  [ Clear ]             │    │
│  └───────────────────────────────────────────────────┘    │
│                                                             │
│  Click any fader to configure it:                          │
│                                                             │
│  ┌─ Fader 1 ─────────────────────────────────────────┐    │
│  │  Action:    [ set_channel_mix ▼ ]                 │    │
│  │  Device:    [ DirtyMixer ▼ ]                      │    │
│  │  Channel:   [ 1 ]                                 │    │
│  │  Range in:  [ 0 ] – [ 127 ]  (MIDI)              │    │
│  │  Range out: [ 0 ] – [ 255 ]  (mix parameter)     │    │
│  └───────────────────────────────────────────────────┘    │
│                                                             │
│  [ Save Mapping ]  [ Load Mapping ]  [ Push to Nexus ]    │
└─────────────────────────────────────────────────────────────┘
```

**Learn mode** — click Learn, press a physical button or move a fader,
Nexus Control detects the MIDI message and assigns it automatically.

**Button colors** — APC Mini Mk2 supports RGB per button. Colors should
match the Joebot device color scheme for intuitive visual feedback:
- MTPX actions → cyan buttons
- DirtyMixer actions → orange buttons
- Atlas actions → green buttons
- TextWall actions → purple buttons
- Unknown → grey buttons

---

## Tab: Registry

View and edit the full device registry. Import/export as .jbt.

```
┌─ Device Registry ───────────────────────────────────────────┐
│                                                             │
│  File: ~/.nexus/jbt/device_registry.jbt                   │
│  Devices: 9  |  Last saved: 2026-03-15 00:10              │
│                                                             │
│  ┌────────────────────────────────────────────────────┐   │
│  │ device_id           type      hostname        en   │   │
│  │ device.mtpx.1       mtpx      mtpx1.ext...   ☑    │   │
│  │ device.mtpx.2       mtpx      mtpx2.ext...   ☑    │   │
│  │ device.mgp.1        mgp       mgp1.extr...   ☑    │   │
│  │ device.mgp.2        mgp       mgp2.extr...   ☑    │   │
│  │ device.mgp.3        mgp       mgp3.extr...   ☑    │   │
│  │ device.matrix.main  matrix    mx.extron...   ☑    │   │
│  │ device.dms.main     dms3600   dms.extro...   ☑    │   │
│  │ device.ipcp505.1    ipcp505   ipcp505-1...   ☑    │   │
│  │ device.dirtymixer.1 dirtymix  USB via App    ☑    │   │
│  └────────────────────────────────────────────────────┘   │
│                                                             │
│  [ + Add Device ]  [ Edit Selected ]  [ Remove Selected ]  │
│  [ Export .jbt ]   [ Import .jbt ]    [ Migrate from JSON ]│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Migrate from JSON** — detects old `devices.json`, converts to
`device_registry.jbt`, archives old file as `devices.json.bak`.

---

## Device Detail Card

Each device card in the Devices tab shows:

### MTPX Detail Card

```
┌─ 🟢 MTPX Plus #1 ──────────────────────────────────────────┐
│  mtpx1.extron.video  •  Rack 1                             │
│  16×16 I/O  Firmware: 1.04  Temp: 86°F  Fans: OK          │
│                                                             │
│  [ Test Connection ] [ View Capabilities ] [ Terminal ]    │
│  [ System Status ]   [ Reset Skew ]        [ Set Blue Max ]│
│                                                             │
│  Input Names:                                               │
│  ┌──────┬────────────────────────────────────┐            │
│  │ IN 1 │ [ VHS Deck 1                     ] │            │
│  │ IN 2 │ [ VHS Deck 2                     ] │            │
│  │ IN 3 │ [ VHSC Deck 1                    ] │            │
│  │ IN 4 │ [ VSC 700D #1 Output             ] │            │
│  └──────┴────────────────────────────────────┘            │
│  [ Edit All Names ]                                        │
│                                                             │
│  Preset Names:                                              │
│  ┌──────┬────────────────────────────────────┐            │
│  │  1   │ [ Clean Signal                   ] │            │
│  │  2   │ [ Max Blue Separation            ] │            │
│  │  3   │ [ VHS Overdrive                  ] │            │
│  └──────┴────────────────────────────────────┘            │
│  [ Edit All Names ]                                        │
└─────────────────────────────────────────────────────────────┘
```

### IPCP 505 Detail Card

```
┌─ 🟢 IPCP 505 #1 ───────────────────────────────────────────┐
│  ipcp505-1.extron.video  •  Rack 1                         │
│  Relays: 8  IR Ports: 8  EIR Files: 2                     │
│                                                             │
│  [ Test Connection ] [ View Capabilities ] [ Terminal ]    │
│  [ EIR Library ]     [ Test Relay 1 ]      [ Test Relay 2 ]│
│                                                             │
│  Serial Port Config:                                        │
│  Port 1: [ RS-232 ▼ ]  Baud: [ 9600 ▼ ]  [ 8N1 ]        │
│  Port 2: [ RS-232 ▼ ]  Baud: [ 9600 ▼ ]  [ 8N1 ]        │
│  Ports 3-8: [ IR ▼ ]                                      │
│                                                             │
│  Relay Names:                                               │
│  Relay 1: [ TitleMaker 2000 Advance ]                     │
│  Relay 2: [ Stage Light Trigger     ]                     │
│                                                             │
│  EIR Library:                                               │
│  File 0 — LGRGB+  (54 commands)  [ Browse ] [ Re-discover]│
│  File 1 — TV_SAMSUNG  (22 commands)  [ Browse ]           │
└─────────────────────────────────────────────────────────────┘
```

---

## Capability Browser

```
┌─ Capabilities — IPCP 505 #1 ────────────────────────┐
│                                                      │
│  Actions:                                           │
│  ▾ pulse_relay                                      │
│      relay  int  1-8  default: 1                   │
│      [ Test with relay=1 ]                         │
│                                                     │
│  ▾ trigger_ir                                       │
│      port     int  1-8   default: 1                │
│      file     int  0-99  default: 0                │
│      command  int  1-126 default: 13               │
│      mode     int  0-2   default: 0                │
│      [ Test with defaults ]                        │
│                                                     │
│  EIR Library:                                       │
│  ▾ File 0 — LGRGB+                                 │
│      1   Power On/Off     [ Fire ]                 │
│      13  Blue             [ Fire ]                 │
│      19  Green            [ Fire ]                 │
│      22  Red              [ Fire ]                 │
│      31  White            [ Fire ]                 │
│      45  Brightness Up    [ Fire ]                 │
│      46  Brightness Down  [ Fire ]                 │
│                                                     │
│           [ Refresh ]              [ Close ]       │
└──────────────────────────────────────────────────────┘
```

---

## SIS Terminal

```
┌─ SIS Terminal ──────────────────────────────────────────┐
│  Device: [ MTPX Plus #1 ▼ ]   [ Common Commands ▼ ]    │
│  ┌─────────────────────────────────────────────────┐    │
│  │ → S↵                                           │    │ orange = sent
│  │ ← +3.28•+4.98•-5.01•+11.52•-12.35•86.88°F    │    │ cyan = received
│  │   Fan1:3590 Fan2:3668 Fan3:3668                │    │ red = error
│  │                                                │    │
│  │ → 1*0*0*31*4Iseq↵                             │    │
│  │ ← Iseq01•00•00•31                             │    │
│  └─────────────────────────────────────────────────┘    │
│  [ S↵ — System status ▼ ]  [ Clear ]  [ Copy Session ]  │
│  ┌──────────────────────────┐                           │
│  │ type command...          │  [ Send ]  [ ↑ History ]  │
│  └──────────────────────────┘                           │
└─────────────────────────────────────────────────────────┘
```

**Common commands snippets per device type:**

MTPX: System status, firmware version, query/set skew, query/reset peaking
IPCP: Pulse relay, fire IR, get EIR file name, get command name
MGP: Firmware version, recall preset, recall preset with inputs
VSC: Firmware version, recall preset, freeze, H/V position, auto image
Matrix: Firmware version, recall preset, tie input to output, query tie
DMS: Firmware version, recall preset, blank/unblank

---

## Add Device Sheet

```
┌─ Add Device ────────────────────────────────────────┐
│                                                      │
│  Device Type  [ IPCP 505 ▼ ]                        │
│                                                      │
│  Device ID    [ device.ipcp505.2              ]     │
│               Auto-suggested, editable              │
│                                                      │
│  Label        [ IPCP 505 #2                   ]     │
│                                                      │
│  Hostname     [ ipcp505-2.extron.video        ]     │
│                                                      │
│  Location     [ Rack 2                        ]     │
│                                                      │
│  Notes        [ Stage right IR and relay      ]     │
│                                                      │
│  Serial ports (IPCP only):                          │
│  [ 9600 ▼ ] baud  [ 8N1 ▼ ]  (default for VSC)    │
│                                                      │
│  [ Test Connection Before Adding ]                  │
│  ✅ Connected — 6ms response                        │
│                                                      │
│  [ Cancel ]                    [ Add Device ]       │
└──────────────────────────────────────────────────────┘
```

---

## Build Priority

### Phase 1 — Device Registry and Status
1. SwiftUI shell with NexusStatusIndicator — Joebot Classic theme
2. Load `device_registry.jbt` from `~/.nexus/jbt/`
3. Device list sidebar with status dots from Nexus
4. Device detail card — basic info display
5. Add/edit/remove devices
6. Save registry back to .jbt
7. Nexus Control registers with Nexus — shows in Observatory
8. Apps tab — show connected app cards with operating mode badges

### Phase 2 — Connection Testing and Quick Actions
9. Test Connection — ping + firmware query
10. Type-specific quick action buttons per device card
11. Connection test result sheet
12. Input/output/preset name editing per device

### Phase 3 — Capability Browser and SIS Terminal
13. Capability browser sheet per device
14. EIR library display for IPCP devices
15. Fire button per IR command and action
16. SIS terminal panel — device selector, history, color coding
17. Common commands snippets per device type

### Phase 4 — MIDI Configuration
18. MIDI tab with virtual APC Mini Mk2 layout
19. Click button to open button config panel
20. RGB color picker for idle and active colors
21. Action selector from Nexus capability discovery
22. Fader config with range mapping
23. Learn mode — press physical button to assign
24. Save/load midi_mapping.jbt
25. Push mapping to Nexus so all apps benefit

### Phase 5 — Polish
26. Import/export registry
27. EIR library editor — add friendly names manually
28. JSON → .jbt migration tool
29. iOS companion for remote device testing

---

## First Session Prompt for Claude Code

> "I am building Nexus Control, a native SwiftUI macOS device administration app for the Joebot Ecosystem. It connects to Nexus via WebSocket and manages the device registry stored in .jbt format. Start by building Phase 1: load the device registry from `~/.nexus/jbt/device_registry.jbt`, show devices in a left sidebar list with green/red status dots from Nexus, show a detail card for the selected device with hostname, type, location, notes, and firmware info. Include a tabbed interface with Devices, Apps, MIDI, and Registry tabs — build the Devices tab first. Include NexusStatusIndicator in the toolbar. Use the Joebot Classic dark theme — dark grey background, orange accents. Read the full spec at https://raw.githubusercontent.com/joebot94/docs/main/NexusControl_BuildGuide.md"

---

## Related Documents

- `Nexus_Architecture.md` — Nexus server spec
- `JBT_Format_Spec.md` — .jbt file format
- `Extron_SIS_Reference.md` — device SIS commands
- `JoebotSDK_Guide.md` — shared Swift toolkit

---

*Nexus Control — Device administration for the Joebot Ecosystem*
*github.com/joebot94/nexus-control*
*Document version 1.1 — March 2026*
*🦖*
