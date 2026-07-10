# JoebotSDK — Shared Swift Toolkit
> Joebot Ecosystem Shared Foundation
> GitHub: github.com/joebot94/joebotsdk
> Document version 1.1 — March 2026
> Changes: Updated theme palette values, added Phosphor Green and Neo Cyberpunk themes,
> improved Amber Terminal colors, added operating mode toggle component,
> added TextWallPreview component, fixed port references to 8675.
> 🦖 Joebot Ecosystem

---

## What JoebotSDK Is

JoebotSDK is a shared Swift package that every Joebot ecosystem app imports.
It contains common code, UI components, data models, and utilities that would
otherwise be duplicated across every app.

Write it once. Every app gets it for free.

---

## Why It Exists

Without a shared SDK every app would:
- Implement Nexus WebSocket connection slightly differently
- Parse .jbt files with slightly different logic
- Show a slightly different Nexus status indicator
- Define slightly different data models for the same concepts
- Drift apart over time as each app evolves independently

With JoebotSDK:
- Fix a Nexus connection bug once — every app gets the fix
- Update the .jbt parser once — every app reads the new format
- Change the Nexus indicator design once — every app looks consistent
- Update a theme once — every app redraws correctly
- Share data models — apps can hand objects to each other cleanly

---

## Tech Stack

| Component | Technology |
|---|---|
| Package type | Swift Package Manager |
| Platform targets | macOS 13+, iOS 16+ |
| UI framework | SwiftUI |
| Networking | Swift Network framework / URLSession WebSocket |
| File I/O | Foundation / Codable |
| Minimum Xcode | 15+ |

---

## What Lives in JoebotSDK

### 1. Nexus Client

The complete Nexus WebSocket connection layer.

**Responsibilities:**
- WebSocket connection management to port 8675
- Auto-reconnection with exponential backoff
- Client registration on connect
- Heartbeat sending every 5 seconds
- Message sending and receiving
- Connection state tracking
- Capability discovery requests
- Operating mode management (Autonomous/Sync/Managed)
- Layout query requests

**Usage in any app:**
```swift
@StateObject var nexus = NexusClient(
    clientId: "textwall_v1",
    clientType: "display",
    operatingMode: .managed,
    capabilities: ["word_mode", "scatter_mode", "16x16"]
)

// Connect — always port 8675
nexus.connect(to: "localhost", port: 8675)

// Send state update
nexus.sendStateUpdate(state: currentGridState)

// Send intent
nexus.sendIntent(
    targets: ["textwall_v1"],
    action: "set_config",
    params: ["grid_size": "3x3", "mode": "word"]
)

// Query another app's layout state
nexus.queryLayout(of: "textwall_v1") { state in
    // state.gridSize, state.activeCells, state.mode
}

// Set operating mode
nexus.setOperatingMode(.sync, source: "textwall_v1", behavior: .invert)

// Receive messages
nexus.onMessage = { message in
    // handle incoming message
}
```

---

### 2. NexusStatusIndicator

The standard Nexus connection indicator. Top right corner of every app.
Consistent design, consistent behavior, consistent position.

**Visual states:**
- 🟢 Green dot — Connected
- 🔴 Red dot — Disconnected
- 🟡 Yellow dot — Connecting / Reconnecting

**Tap → opens NexusSettingsPopover:**

```
┌─ Nexus ──────────────────────────────┐
│  🟢 Connected                        │
│                                      │
│  Server                              │
│  [ localhost                      ]  │
│                                      │
│  Port                                │
│  [ 8675 ]                            │
│                                      │
│  ☑ Auto-connect on launch            │
│                                      │
│  Connected as: textwall_v1           │
│  Uptime: 00:42:17                    │
│                                      │
│  Operating Mode:                     │
│  [ Managed ▼ ]                       │
│                                      │
│  [ Disconnect ]                      │
└──────────────────────────────────────┘
```

**Usage:**
```swift
ToolbarItem(placement: .topBarTrailing) {
    NexusStatusIndicator(client: nexus)
}
```

One line. Every app gets consistent Nexus status UI.

---

### 3. Operating Mode Toggle

A compact UI component showing and controlling the current operating mode.
Displayed in the NexusStatusIndicator popover and optionally in the main toolbar.

```
┌─ Operating Mode ─────────────────────┐
│                                      │
│  [ 🤖 Autonomous | 🔄 Sync | 📡 Managed ]  │
│                                      │
│  Sync source: [ textwall_v1 ▼ ]     │
│  Behavior:    [ Invert ▼ ]          │
│                                      │
└──────────────────────────────────────┘
```

**Usage:**
```swift
OperatingModeToggle(client: nexus)
```

---

### 4. JBT Parser and Writer

Complete .jbt file read/write shared across all apps.

```swift
// Reading
let session = try JBT.load(from: url, as: GlitchSession.self)
let lyrics  = try JBT.load(from: url, as: LyricTimeline.self)
let setlist = try JBT.load(from: url, as: DAWSetlist.self)

// Writing
try JBT.save(session, to: url)
try JBT.save(lyrics, to: url)

// Type detection — read jbt_type without full parse
let type = try JBT.detectType(at: url)
// Returns "glitch_session", "lyric_timeline", "daw_setlist" etc.

// Version check
let supported = JBT.isSupportedVersion(at: url)
```

Handles versioning, unknown fields, migration between versions.

---

### 5. Shared Data Models

Swift structs for data types that multiple apps need to understand.

**Models included:**
- `NexusMessage` — standard message envelope
- `ClientRegistration` — registration payload
- `ClientCapabilities` — capability discovery response
- `JBTRoot` — base .jbt file structure
- `GlitchSession` — glitch_session .jbt type
- `DirtyMixerPreset` — dirtymixer_preset .jbt type
- `DirtyMixerChannel` — per channel state
- `ExtronSnapshot` — extron_snapshot .jbt type
- `NexusScene` — nexus_scene .jbt type
- `LyricTimeline` — lyric_timeline v2.0 .jbt type
- `LyricCue` — individual lyric cue with TextWall config
- `TextWallConfig` — TextWall display configuration per cue
- `TextWallLayout` — saved named layout .jbt type
- `DAWSetlist` — daw_setlist .jbt type
- `MIDIMapping` — midi_mapping .jbt type

---

### 6. Joebot Theme System

Complete SwiftUI theming system. All apps share the same theme definitions.
Switch themes — entire app redraws instantly. One update propagates everywhere.

**Available themes:**

| Theme ID | Name | Description |
|---|---|---|
| `joebot` | Joebot Classic | Dark grey background, orange accents — default |
| `joebot_black` | Joebot Black | Full black, orange accents, high contrast |
| `cyberpunk` | Neo Cyberpunk | Deep purple/black, cyan + magenta neon |
| `dos` | DOS / Win3.11 | Navy background, cyan/white text — retro terminal |
| `amber` | Amber Terminal | Near-black background, rich phosphor amber |
| `phosphor` | Phosphor Green | Near-black background, classic CRT green glow |

**Theme color values:**

```swift
// Joebot Classic
background:  #1C1C1E
surface:     #2C2C2E
accent:      #FF6600  // orange
text:        #FFFFFF
textSecondary: #888888
border:      #3C3C3E

// DOS / Win3.11
background:  #000080  // navy
surface:     #0000AA
accent:      #00FFFF  // cyan
text:        #FFFFFF
textSecondary: #AAAAAA
border:      #0000CC

// Amber Terminal — rich phosphor, NOT pale yellow
background:  #0D0800  // near black, warm tint
surface:     #180E00
accent:      #FF8C00  // hot amber, almost burning
text:        #FFB000  // proper phosphor amber
textSecondary: #CC6600
border:      #3D2200
highlight:   #FFCC44  // bright phosphor bloom

// Neo Cyberpunk
background:  #0A0015  // near black, deep purple tint
surface:     #150025
accent:      #00FFFF  // electric cyan
accent2:     #FF00FF  // neon magenta
text:        #E0E0FF  // cool white with purple tint
textSecondary: #8866CC
border:      #4400AA  // deep purple
highlight:   #00FFAA  // cyan-green neon
active:      #FF00AA  // hot pink

// Phosphor Green
background:  #000D00  // near black, green tint
surface:     #001500
accent:      #00FF41  // matrix green
text:        #00FF41
textSecondary: #007722
border:      #004400
highlight:   #AAFFAA  // bright phosphor bloom
dim:         #003311  // low intensity phosphor
```

**Usage:**
```swift
@main
struct TextWallApp: App {
    @StateObject var theme = JoebotTheme(initial: .joebot)

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(theme)
        }
    }
}

// Switch theme — entire app redraws
JoebotTheme.current.set(.amber)
```

**Theme definition structure:**
```swift
struct ThemeDefinition {
    let id: String
    let name: String
    let background: Color
    let surface: Color
    let accent: Color
    let accent2: Color?
    let text: Color
    let textSecondary: Color
    let border: Color
    let success: Color
    let warning: Color
    let error: Color
    let highlight: Color
    let fontPrimary: String
    let fontMono: String
}
```

---

### 7. Common UI Components

| Component | Description |
|---|---|
| `NexusStatusIndicator` | Nexus connection dot and settings popover |
| `OperatingModeToggle` | Autonomous/Sync/Managed mode switcher |
| `JoebotButton` | Standard themed button |
| `StatusDot` | Green/yellow/red status indicator dot |
| `SectionHeader` | Consistent section header style |
| `EmptyStateView` | Standard empty state with 🦖 and message |
| `LoadingView` | Standard loading indicator |
| `ErrorBanner` | Non-intrusive error display |
| `CapabilityGrid` | Dynamic grid built from capability data |
| `PresetGrid` | Tappable preset selector grid |
| `ChannelSelector` | Multi-select channel picker |
| `TextWallPreview` | Mini animated TextWall grid preview |
| `CellLayoutPicker` | Tap-to-toggle freeform cell picker |

#### TextWallPreview

Mini animated preview of a TextWall configuration.
Used in GlitchBoard cue editor, Lyric App cue editor, hover tooltips.

```swift
// Static preview
TextWallPreview(
    config: textWallConfig,
    text: "welcome to the machine",
    animated: false
)

// Animated preview (scatter/reveal modes animate live)
TextWallPreview(
    config: textWallConfig,
    text: "welcome to the machine",
    animated: true
)
```

```
┌───────┬───────┬───────┐
│  WEL  │  TO   │  THE  │
│  COME │       │       │
├───────┼───────┼───────┤
│       │ MACH  │       │
│       │  INE  │       │
├───────┼───────┼───────┤
│       │       │       │
│       │       │       │
└───────┴───────┴───────┘
```

#### CellLayoutPicker

Freeform cell picker — tap any cell to toggle active/inactive.
Saves as named layout. Every preset is just a saved freeform selection.

```swift
CellLayoutPicker(
    gridSize: GridSize(rows: 3, cols: 3),
    activeCells: $activeCells,
    onSave: { name in
        // save as named layout
    }
)
```

```
┌───┬───┬───┐
│ ☑ │ ☐ │ ☑ │  ← tap cells to toggle
├───┼───┼───┤
│ ☐ │ ☑ │ ☐ │
├───┼───┼───┤
│ ☑ │ ☐ │ ☑ │
└───┴───┴───┘
[ Save Layout... ]  Name: [ X Pattern ]
```

---

## Capability Discovery Helper

```swift
// Ask Nexus what TextWall can do
nexus.queryCapabilities(of: "textwall_v1") { capabilities in
    // capabilities.gridSizes
    // capabilities.modes
    // capabilities.layouts
    // capabilities.maxHz
    // Build your UI from this
}

// Ask Nexus what the MTPX can do
nexus.queryCapabilities(of: "device.mtpx.1") { capabilities in
    // capabilities.actions[0].action == "set_input_skew"
    // capabilities.actions[0].params["blue"].range == [0, 31]
}
```

---

## App Integration Pattern

Every Joebot app follows this pattern:

```swift
@main
struct TextWallApp: App {
    @StateObject var nexus = NexusClient(
        clientId: "textwall_v1",
        clientType: "display",
        operatingMode: .managed,
        capabilities: ["word_mode", "scatter_mode", "reveal_mode", "16x16"]
    )
    @StateObject var theme = JoebotTheme(initial: .joebot)

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(nexus)
                .environmentObject(theme)
        }
    }
}
```

Every view in the app has access to Nexus client and theme via environment.

---

## Graceful Nexus Degradation

Every app handles Nexus being unavailable gracefully:

```swift
if nexus.isConnected {
    // Show full feature set
    SnapshotButton()
    NexusDependentFeature()
} else {
    // Degraded but functional
    SnapshotButton().disabled(true)
    Text("Connect to Nexus to enable").foregroundColor(.secondary)
}
```

Features that require Nexus are disabled with clear visual indicators when offline.
Apps never crash or error because Nexus is offline.

---

## Repo Structure

```
joebotsdk/
├── Package.swift
├── README.md
├── Sources/
│   └── JoebotSDK/
│       ├── Nexus/
│       │   ├── NexusClient.swift
│       │   ├── NexusMessage.swift
│       │   ├── NexusState.swift
│       │   ├── OperatingMode.swift        ← NEW
│       │   └── CapabilityDiscovery.swift
│       ├── JBT/
│       │   ├── JBTParser.swift
│       │   ├── JBTWriter.swift
│       │   └── Models/
│       │       ├── GlitchSession.swift
│       │       ├── DirtyMixerPreset.swift
│       │       ├── DirtyMixerTimeline.swift
│       │       ├── ExtronSnapshot.swift
│       │       ├── LyricTimeline.swift     ← NEW
│       │       ├── TextWallLayout.swift    ← NEW
│       │       └── DAWSetlist.swift        ← NEW
│       ├── UI/
│       │   ├── NexusStatusIndicator.swift
│       │   ├── OperatingModeToggle.swift   ← NEW
│       │   ├── TextWallPreview.swift       ← NEW
│       │   ├── CellLayoutPicker.swift      ← NEW
│       │   ├── CapabilityGrid.swift
│       │   ├── PresetGrid.swift
│       │   ├── ChannelSelector.swift
│       │   └── Common/
│       │       ├── JoebotButton.swift
│       │       ├── StatusDot.swift
│       │       └── SectionHeader.swift
│       └── Theme/
│           ├── JoebotTheme.swift
│           ├── ThemeDefinition.swift
│           └── Themes/
│               ├── JoebotClassic.swift
│               ├── JoebotBlack.swift
│               ├── NeoCyberpunk.swift      ← UPDATED colors
│               ├── DOS.swift
│               ├── Amber.swift             ← UPDATED — richer phosphor
│               └── PhosphorGreen.swift     ← NEW
└── Tests/
    └── JoebotSDKTests/
```

---

## Build Priority

1. NexusClient — WebSocket connection, registration, heartbeat, port 8675
2. NexusStatusIndicator — the universal Nexus dot
3. JoebotTheme — all themes with updated color values
4. OperatingMode system — Autonomous/Sync/Managed
5. JBT parser/writer — all types including lyric_timeline v2.0
6. Shared data models — LyricTimeline, TextWallLayout, DAWSetlist
7. TextWallPreview — mini animated grid preview
8. CellLayoutPicker — freeform cell toggle picker
9. CapabilityGrid and PresetGrid
10. Remaining UI components

---

## First Session Prompt for Claude Code

> "I am building JoebotSDK, a Swift Package shared across all apps in the Joebot Ecosystem. Start by building the NexusClient class that manages a WebSocket connection to Nexus on port 8675, handles registration with operating mode support (Autonomous/Sync/Managed), sends heartbeats every 5 seconds, tracks connection state, and exposes a simple API for sending and receiving messages. Then build NexusStatusIndicator showing a green/yellow/red dot with a settings popover including server hostname, port (default 8675), operating mode toggle, uptime display, and disconnect button. Then build the JoebotTheme system with all six themes: Joebot Classic, Joebot Black, Neo Cyberpunk, DOS/Win3.11, Amber Terminal, and Phosphor Green — using the exact color values in JoebotSDK_Guide.md. Read the full spec at https://raw.githubusercontent.com/joebot94/docs/main/JoebotSDK_Guide.md"

---

## Related Documents

- `Nexus_Architecture.md` — Nexus server spec
- `Observatory_BuildGuide.md` — Observatory app spec
- `DirtyMixerApp_BuildGuide.md` — DirtyMixerApp spec
- `TextWall_BuildGuide.md` — TextWall display app spec
- `LyricApp_BuildGuide.md` — Lyric App authoring spec
- `JBT_Format_Spec.md` — .jbt file format reference

---

*JoebotSDK — Shared Swift foundation for the Joebot ecosystem*
*github.com/joebot94/joebotsdk*
*Document version 1.1 — March 2026*
*🦖*
