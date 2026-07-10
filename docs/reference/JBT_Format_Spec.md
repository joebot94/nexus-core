# JBT Format Specification
> Joebot Ecosystem Shared File Format
> GitHub: github.com/joebot94/docs
> Document version 1.1 — March 2026
> Changes: Added new types (lyric_timeline v2.0, textwall_layout, daw_setlist,
> nexus_device_registry, nexus_eir_library, midi_mapping, app_prefs,
> capabilities_cache). Added .jbt mandate section. Updated storage locations.
> 🦖 Joebot Ecosystem

---

## The .jbt Mandate

**Every file in the Joebot ecosystem is .jbt. No exceptions.**

JSON is the encoding format under the hood. `.jbt` is the contract on top.
The `jbt_type` field at the root tells every app exactly what it's looking at.

If it stores data, it's `.jbt`.
If it's config, it's `.jbt`.
If it's a preference file, it's `.jbt`.
If Nexus touches it, it's `.jbt`.

There are no `.json` config files anywhere in the ecosystem.

---

## What .jbt Is

`.jbt` is the shared file format for the entire Joebot studio ecosystem.
Plain JSON under the hood, human readable, version tracked, extensible.

Every Joebot app reads and writes `.jbt` files. Nexus uses `.jbt` for everything.
Glitch Catalog stores sessions as `.jbt`. DirtyMixerApp saves presets as `.jbt`.
TextWall saves layouts as `.jbt`. GlitchBoard saves setlists as `.jbt`.

---

## Core Principles

- Every .jbt file is valid JSON
- Every .jbt file has a `jbt_type` field at the root
- Every .jbt file has a `version` field at the root
- Every .jbt file has a `created_at` timestamp at the root
- Apps only process types they understand — unknown types are ignored gracefully
- The format evolves via version field — old files remain readable
- Unknown fields are always ignored, never errored on

---

## Root Envelope

Every .jbt file regardless of type shares this root structure:

```json
{
  "jbt_type": "string",
  "version": "1.0",
  "created_at": "2026-03-15T00:00:00Z",
  "name": "Human readable name",
  "notes": "Optional notes",
  "payload": { ... }
}
```

| Field | Required | Description |
|---|---|---|
| `jbt_type` | Yes | Identifies the object type |
| `version` | Yes | Format version for this type |
| `created_at` | Yes | ISO 8601 timestamp |
| `modified_at` | Optional | Set when file is updated |
| `name` | Recommended | Human readable name |
| `notes` | Optional | Free text notes |
| `payload` | Yes | Type-specific content |

---

## Complete JBT Type Registry

| jbt_type | App | Description |
|---|---|---|
| `dirtymixer_preset` | DirtyMixerApp | Board state snapshot — all 9 channels |
| `dirtymixer_timeline` | DirtyMixerApp | Keyframed automation over time |
| `dirtymixer_clip` | DirtyMixerApp | Reusable automation segment |
| `dirtymixer_project` | DirtyMixerApp | Full session — presets + timelines |
| `extron_snapshot` | Atlas | Extron device state snapshot |
| `glitch_session` | Glitch Catalog | Full studio session with event log |
| `nexus_scene` | Nexus | Cross-app scene definition |
| `nexus_pattern` | Nexus | Timed behavior pattern |
| `nexus_cue_bundle` | Nexus | Collection of cues for show playback |
| `nexus_event_log` | Nexus | Rolling event log from event logger |
| `nexus_device_registry` | Nexus Control | All device configs — replaces devices.json |
| `nexus_eir_library` | Nexus Control | IR command library per IPCP device |
| `textwall_state` | TextWall | Text content and style for scene recall |
| `textwall_layout` | TextWall | Saved named layout configuration |
| `lyric_timeline` | Lyric App | Lyrics synced to audio with TextWall config |
| `daw_setlist` | GlitchBoard | Full show — songs + cues + device lanes |
| `midi_mapping` | Nexus Control | APC Mini / controller button assignments |
| `app_prefs` | Any app | Per-app user preferences |
| `capabilities_cache` | GlitchBoard | Cached Nexus capability responses |

New types are added as new apps join the ecosystem.
Existing apps ignore unknown types gracefully — never error.

---

## Type Definitions

---

### dirtymixer_preset

A complete snapshot of all 9 dirty mixer channel states.

```json
{
  "jbt_type": "dirtymixer_preset",
  "version": "1.0",
  "created_at": "2026-03-13T00:00:00Z",
  "name": "Chaos Mode",
  "notes": "High energy all channels fighting",
  "payload": {
    "channels": [
      {
        "id": 1,
        "input_a_enabled": true,
        "input_b_enabled": true,
        "mix": 128
      },
      {
        "id": 2,
        "input_a_enabled": true,
        "input_b_enabled": false,
        "mix": 255
      }
    ],
    "transition": {
      "type": "linear",
      "duration_ms": 0
    }
  }
}
```

---

### dirtymixer_timeline

Keyframed automation for dirty mixer channels over time.

```json
{
  "jbt_type": "dirtymixer_timeline",
  "version": "1.0",
  "created_at": "2026-03-13T00:00:00Z",
  "name": "10 Second Chaos Ramp",
  "payload": {
    "duration_ms": 10000,
    "tracks": [
      {
        "channel_ids": [1, 4, 6, 9],
        "parameter": "mix",
        "keyframes": [
          { "time_ms": 0, "value": 0 },
          { "time_ms": 5000, "value": 120 },
          { "time_ms": 10000, "value": 0 }
        ],
        "interpolation": "linear"
      },
      {
        "channel_ids": [7],
        "parameter": "mix",
        "mode": "random",
        "random_interval_ms": 500
      }
    ]
  }
}
```

---

### glitch_session

Full studio session — the primary Glitch Catalog record type.

```json
{
  "jbt_type": "glitch_session",
  "version": "1.0",
  "created_at": "2026-02-25T00:00:00Z",
  "name": "Basement Burn-In",
  "payload": {
    "date": "2026-02-25",
    "location": "Studio A",
    "tags": ["RGB Skew", "VHS", "Feedback"],
    "scene_snapshot": {
      "dirtymixer_preset": { ... },
      "extron_snapshot": { ... },
      "textwall_state": { ... }
    },
    "analog_masters": [
      {
        "id": "VH01S1",
        "label": "VHS — Joebot Glitches VH01S1 — 1",
        "format": "VHS",
        "tape_number": 1
      }
    ],
    "gear_chain": [
      { "label": "MTPX Plus 1616" },
      { "label": "Dirty Mixer Board" },
      { "label": "Panasonic WJ-AVE5" }
    ],
    "digital_captures": [
      {
        "filename": "20260225_basement_burnin.mp4",
        "duration_s": 7.2,
        "resolution": "1920x1080",
        "codec": "hevc",
        "tags": ["capture"]
      }
    ],
    "event_log": {
      "session_id": "session_001",
      "started_at": "2026-02-25T00:32:00.000Z",
      "stopped_at": "2026-02-25T02:15:00.000Z",
      "duration_seconds": 6180,
      "events": [
        {
          "timestamp": "2026-02-25T00:32:01.234Z",
          "relative_ms": 1234,
          "type": "state_update",
          "source": "dirtymixer_v1",
          "summary": "CH3 mix changed to 194",
          "payload": { "channels": [{"id": 3, "mix": 194}] }
        }
      ]
    }
  }
}
```

---

### nexus_device_registry

All device configuration for the ecosystem. Replaces devices.json entirely.
Stored at: `~/.nexus/jbt/device_registry.jbt`

```json
{
  "jbt_type": "nexus_device_registry",
  "version": "1.0",
  "created_at": "2026-03-15T00:00:00Z",
  "name": "Joebot Studio Device Registry",
  "payload": {
    "devices": [
      {
        "device_id": "device.mtpx.1",
        "type": "mtpx",
        "hostname": "mtpx1.extron.video",
        "label": "MTPX Plus 1616",
        "location": "Rack 1",
        "notes": "Primary RGB skew unit",
        "enabled": true
      },
      {
        "device_id": "device.ipcp505.1",
        "type": "ipcp505",
        "hostname": "ipcp505-1.extron.video",
        "label": "IPCP 505 #1",
        "location": "Rack 1",
        "notes": "Stage left IR and relay",
        "enabled": true
      }
    ]
  }
}
```

---

### nexus_eir_library

IR command library auto-discovered from an IPCP device.
Stored at: `~/.nexus/jbt/eir_library_{device_id}.jbt`

```json
{
  "jbt_type": "nexus_eir_library",
  "version": "1.0",
  "created_at": "2026-03-15T00:00:00Z",
  "name": "IPCP 505 #1 EIR Library",
  "payload": {
    "device_id": "device.ipcp505.1",
    "discovered_at": "2026-03-15T00:00:00Z",
    "eir_files": [
      {
        "file_number": 0,
        "filename": "LGRGB+",
        "device_description": "LG RGB LED Strip",
        "commands": {
          "1": "Power On/Off",
          "13": "Blue",
          "19": "Green",
          "22": "Red",
          "31": "White",
          "45": "Brightness Up",
          "46": "Brightness Down"
        }
      }
    ]
  }
}
```

---

### textwall_layout

A saved named TextWall display configuration.
Stored at: `~/JBT/textwall/layouts/`

```json
{
  "jbt_type": "textwall_layout",
  "version": "1.0",
  "created_at": "2026-03-15T00:00:00Z",
  "name": "Welcome to the Machine — Closing Shot",
  "payload": {
    "grid_size": "16x16",
    "active_cells": "all",
    "mode": "scatter",
    "scatter_instances": 8,
    "scatter_hz": 10,
    "font": "Helvetica Neue",
    "weight": "bold",
    "color": "#FFFFFF",
    "background": "#000000",
    "transition": "cut"
  }
}
```

---

### lyric_timeline v2.0

Lyrics synced to audio with full TextWall configuration per cue.
Authored in Lyric App. Importable into GlitchBoard as TextWall lane cues.

```json
{
  "jbt_type": "lyric_timeline",
  "version": "2.0",
  "created_at": "2026-03-15T00:00:00Z",
  "name": "Welcome to the Machine",
  "payload": {
    "audio_file": "~/Music/welcome_to_the_machine.wav",
    "audio_duration_s": 482.0,
    "bpm": 72,
    "time_signature": "4/4",
    "hardware_config": {
      "enabled": true,
      "device_id": "device.ipcp505.1",
      "action": "pulse_relay",
      "relay": 2,
      "pulse_duration_ms": 100
    },
    "lyrics": [
      {
        "id": "lyric_001",
        "time": 62.5,
        "bar": 8,
        "beat": 1,
        "text": "welcome, my son",
        "style": "verse",
        "hardware_advance": true,
        "textwall": {
          "grid_size": "3x3",
          "layout": "center_row",
          "mode": "word",
          "font": "Helvetica Neue",
          "weight": "bold",
          "color": "#FFFFFF",
          "background": "#000000",
          "transition": "cut"
        }
      },
      {
        "id": "lyric_clear_001",
        "time": 67.8,
        "type": "clear",
        "text": null,
        "textwall": null
      },
      {
        "id": "lyric_scatter_final",
        "time": 421.0,
        "text": "welcome to the machine",
        "style": "chorus",
        "hardware_advance": false,
        "textwall": {
          "grid_size": "16x16",
          "layout": "all_cells",
          "mode": "scatter",
          "scatter_instances": 8,
          "scatter_hz": 10,
          "color": "#FFFFFF",
          "background": "#000000"
        }
      }
    ]
  }
}
```

---

### daw_setlist

Full GlitchBoard show — songs, cues, device lanes, TextWall lane included.

```json
{
  "jbt_type": "daw_setlist",
  "version": "1.0",
  "created_at": "2026-03-14T00:00:00Z",
  "name": "Show A — March 2026",
  "payload": {
    "songs": [
      {
        "id": "song_001",
        "title": "Welcome to the Machine",
        "audio_path": "~/Music/welcome_to_the_machine.wav",
        "bpm": 72,
        "time_signature": "4/4",
        "cues": [ ... ],
        "transition": { "type": "immediate", "transition_cues": [] }
      }
    ],
    "global_cue_library": [ ... ],
    "device_lanes": [
      {
        "device_id": "device.mtpx.1",
        "label": "MTPX Plus #1",
        "color": "#00FFFF",
        "offline_behavior": "skip"
      },
      {
        "device_id": "textwall_v1",
        "label": "TextWall",
        "color": "#AA00FF",
        "offline_behavior": "skip"
      }
    ],
    "midi_mappings": [ ... ]
  }
}
```

---

### midi_mapping

APC Mini Mk2 or other controller button/fader assignments.
Stored at: `~/.nexus/jbt/midi_mapping_{controller_id}.jbt`
All apps get mapping from Nexus — configured once, used everywhere.

```json
{
  "jbt_type": "midi_mapping",
  "version": "1.0",
  "created_at": "2026-03-15T00:00:00Z",
  "name": "APC Mini Mk2 — Main Show",
  "payload": {
    "controller": "APC Mini Mk2",
    "mappings": [
      {
        "button": {"row": 1, "col": 1},
        "idle_color": "#004444",
        "active_color": "#00FFFF",
        "action": "recall_preset",
        "device_id": "device.dirtymixer.1",
        "params": {"preset_id": 12}
      },
      {
        "fader": 1,
        "action": "set_channel_mix",
        "device_id": "device.dirtymixer.1",
        "params": {"channel": 1},
        "range_in": [0, 127],
        "range_out": [0, 255]
      }
    ]
  }
}
```

---

### app_prefs

Per-app user preferences. Stored in app's JBT folder.

```json
{
  "jbt_type": "app_prefs",
  "version": "1.0",
  "created_at": "2026-03-15T00:00:00Z",
  "name": "GlitchBoard Preferences",
  "payload": {
    "app_id": "glitchboard",
    "theme": "joebot",
    "nexus_host": "localhost",
    "nexus_port": 8675,
    "nexus_autoconnect": true,
    "default_snap": "1/4",
    "default_zoom": "fit"
  }
}
```

---

### capabilities_cache

Cached Nexus capability responses. No more capabilities_cache.json.
Stored at: `~/JBT/glitchboard/capabilities_cache.jbt`

```json
{
  "jbt_type": "capabilities_cache",
  "version": "1.0",
  "created_at": "2026-03-15T00:00:00Z",
  "payload": {
    "cached_at": "2026-03-15T00:00:00Z",
    "devices": {
      "device.mtpx.1": {
        "actions": [ ... ],
        "cached_at": "2026-03-15T00:00:00Z"
      },
      "textwall_v1": {
        "grid_sizes": ["1x1","2x2","3x3","4x4","8x8","16x16"],
        "modes": ["line","word","letter","scatter","reveal"],
        "cached_at": "2026-03-15T00:00:00Z"
      }
    }
  }
}
```

---

## Versioning

Each type has its own version field. Version follows semver lite:

- `1.0` — initial stable definition
- `1.1` — backwards compatible additions
- `2.0` — breaking changes

Apps handle unknown fields gracefully — ignore rather than error.
Apps warn if they encounter a version higher than they support.

---

## File Naming Conventions

| Type | Naming Pattern |
|---|---|
| `dirtymixer_preset` | `preset_{name}.jbt` |
| `dirtymixer_timeline` | `timeline_{name}.jbt` |
| `dirtymixer_project` | `project_{name}.jbt` |
| `glitch_session` | `{date}_{name}.jbt` |
| `nexus_scene` | `scene_{id}.jbt` |
| `nexus_pattern` | `pattern_{id}.jbt` |
| `lyric_timeline` | `{song_name}_lyrics.jbt` |
| `textwall_layout` | `layout_{name}.jbt` |
| `daw_setlist` | `{show_name}_setlist.jbt` |
| `midi_mapping` | `midi_{controller}.jbt` |

---

## File Storage Locations

| App | Type | Path |
|---|---|---|
| Nexus | device_registry | `~/.nexus/jbt/device_registry.jbt` |
| Nexus | eir_library | `~/.nexus/jbt/eir_library_{device_id}.jbt` |
| Nexus | scenes | `~/.nexus/jbt/scenes/` |
| Nexus | patterns | `~/.nexus/jbt/patterns/` |
| Nexus | midi_mapping | `~/.nexus/jbt/midi_mapping_{controller}.jbt` |
| Nexus | event_log | `~/.nexus/logs/nexus_rolling.jbt` |
| Glitch Catalog | glitch_session | `~/JBT/sessions/` |
| DirtyMixerApp | presets | `~/JBT/dirtymixer/presets/` |
| DirtyMixerApp | projects | `~/JBT/dirtymixer/projects/` |
| GlitchBoard | daw_setlist | `~/JBT/glitchboard/setlists/` |
| GlitchBoard | capabilities_cache | `~/JBT/glitchboard/capabilities_cache.jbt` |
| GlitchBoard | app_prefs | `~/JBT/glitchboard/prefs.jbt` |
| TextWall | textwall_layout | `~/JBT/textwall/layouts/` |
| Lyric App | lyric_timeline | `~/JBT/lyrics/` |

---

## Parsing Guidelines

Any app parsing .jbt files should:

1. Read `jbt_type` first — if unknown, skip gracefully, never error
2. Check `version` — warn if higher than supported version
3. Parse `payload` according to type schema
4. Ignore unknown fields rather than erroring
5. Never modify a .jbt file without updating or adding `modified_at`
6. Always write valid JSON — pretty-printed for human readability

---

## Related Documents

- `Nexus_Architecture.md` — Nexus server spec
- `DirtyMixerApp_BuildGuide.md` — DirtyMixerApp spec
- `TextWall_BuildGuide.md` — TextWall display app spec
- `LyricApp_BuildGuide.md` — Lyric App authoring spec
- `GlitchBoard_Spec.md` — GlitchBoard DAW spec

---

*JBT Format Specification*
*github.com/joebot94/docs*
*Document version 1.1 — March 2026*
*🦖*
