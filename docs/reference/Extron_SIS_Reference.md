# Extron SIS Command Reference
> Human-readable translation of Extron SIS protocol commands
> GitHub: github.com/joebot94/docs
> Document version 1.1 — March 2026
> Changes: Added full MTPX Plus section including skew and pre-peaking commands
> 🦖 Joebot Ecosystem

---

## How to Read This Document

Extron SIS (Simple Instruction Set) is the serial control protocol used by all Extron devices. Commands are sent as ASCII text over TCP port 23 (Telnet) or via serial connection through an IPCP/IPL. Every command ends with a carriage return `↵`.

### Notation Used in This Document

| Symbol | Meaning |
|---|---|
| `↵` | Carriage return — send this at the end of every command |
| `{value}` | A number you supply |
| `{in}` | Input number |
| `{out}` | Output number |
| `{n}` | Preset number |
| `0` | Zero — Extron docs sometimes use Ø to distinguish from letter O |
| `[alone]` | Sending the command letter alone queries the current value |
| `+cmd` | Increment by one step |
| `-cmd` | Decrement by one step |
| `{value}*{fn}#` | Special function syntax — set function fn to value |
| `{fn}#` | Special function query — get current value of function fn |

### Universal Patterns

These patterns apply across almost all Extron devices:

**Query current value:** Send command letter alone
```
H↵  →  returns current horizontal position
```

**Set specific value:** Send value then command letter
```
128H↵  →  set horizontal position to 128
```

**Increment/Decrement:** Send + or - then command letter
```
+H↵  →  shift right one step
-H↵  →  shift left one step
```

**Preset recall:** Always period after number
```
1.↵  →  recall preset 1
```

**Preset save:** Always comma after number
```
1,↵  →  save to preset 1
```

**Special function set:** value * function_number #
```
1*14#↵  →  set function 14 to value 1
```

**Special function query:** function_number # alone
```
14#↵  →  query current value of function 14
```

### Universal Extron Notes

- Default TCP port: **23** (Telnet)
- All commands end with carriage return `↵`
- Responses end with carriage return
- Preset recall syntax `{n}.↵` is consistent across ALL Extron devices
- Preset save syntax `{n},↵` is consistent across ALL Extron devices

---

## Device: MTPX Plus Series
> Extron Matrix Switcher with RGB Skew and Pre-peaking
> Connection: TCP port 23
> Hostnames: mtpx1.extron.video, mtpx2.extron.video
> Joebot use: RGB skew abuse for chromatic aberration glitch effect, pre-peaking voltage boost for VHS-style brightness overdrive, central matrix routing

### ⭐ Why This Device Matters for Glitch Art

The MTPX Plus is the core of the Joebot glitch technique. Two specific features make it unique:

**RGB Skew** — Each color plane (R, G, B) can be delayed independently by 2ns increments up to 31 steps (62ns). Deliberately over-applying skew creates hardware chromatic aberration — the RGB planes separate visually creating that signature color-shifted glitch look. Fewer than 5 people in the world are doing this intentionally.

**Pre-peaking** — A voltage boost applied before the signal is processed. Abusing this creates VHS-style brightness overdrive — the signal clips and blooms in a distinctly analog way.

Both of these can be captured in session snapshots and recalled precisely via Nexus. This is what makes glitch art reproducible.

---

### Tie Commands (Matrix Routing)

| What you want | Send | Response |
|---|---|---|
| Tie input to output (video+audio) | `{in}*{out}!↵` | `Out{out}•In{in}•All↵` |
| Tie input to output (RGB video only) | `{in}*{out}&↵` | `In{in}@RGB↵` |
| Tie input to output (video only) | `{in}*{out}%↵` | `In{in}@Vid↵` |
| Tie input to output (audio only) | `{in}*{out}$↵` | `In{in}@Aud↵` |
| Tie input to ALL outputs | `{in}*1↵` | `In{in}@All↵` |
| Quick multiple tie | `{in1}*{out1}*{in2}*{out2}...!↵` | `Qik↵` |

**Example:** Tie input 1 to output 3 (video+audio):
```
1*3!↵  →  Out03•In01•All↵
```

**Example:** Tie input 10 RGB only to output 4:
```
10*4&↵  →  In10@RGB↵
```

### Read Ties (Query Current Routing)

| What you want | Send | Response |
|---|---|---|
| Read RGB video output tie | `{out}A↵` | `{in}↵` |
| Read video output tie | `{out}B↵` | `{in}↵` |
| Read audio output tie | `{out}C↵` | `{in}↵` |

**Example:** What input is tied to output 5 RGB?
```
5A↵  →  12↵  (input 12 is tied to output 5)
```

---

### Presets

| What you want | Send | Response |
|---|---|---|
| Save current config as preset | `{n},↵` | `Spr{n}↵` |
| Recall a preset | `{n}.↵` | `Rpr{n}↵` |
| Write preset name | `{n}*{name}Nmp↵` | `Nmp{n}•{name}↵` |
| Read preset name | `{n}*Nmp↵` | `{name}↵` |

Same syntax as every other Extron device. Consistent across the ecosystem. 🦖

---

### ⭐⭐ Input Skew Adjustment (Chromatic Aberration Technique)

> Note: For MTPX Plus 128, valid for inputs 5-12 only.

**Video plane values:**
- `0` = Red
- `1` = Green
- `2` = Blue

**Skew range:** 0-31 steps (each step = 2ns, max = 62ns delay)

| What you want | Send | Response |
|---|---|---|
| Set all skew values (R, G, B) | `{in}*{R}*{G}*{B}*4Iseq↵` | `Iseq{in}•{R}•{G}•{B}↵` |
| Increment one plane skew by 1 step | `{in}*{plane}*1Iseq↵` | `Iseq{in}•{R}•{G}•{B}↵` |
| Decrement one plane skew by 1 step | `{in}*{plane}*-1Iseq↵` | `Iseq{in}•{R}•{G}•{B}↵` |
| Read input skew values | `{in}*Iseq↵` | `{R}•{G}•{B}↵` |

**Example:** Set input 2 skew to R=0, G=0, B=8ns (4 steps):
```
2*0*0*4*4Iseq↵  →  Iseq02•00•00•04↵
```

**Example:** Increase blue skew on input 2 by 2ns (1 step):
```
2*2*1Iseq↵  →  Iseq02•00•00•05↵
```

**Glitch technique note:** To create chromatic aberration, set blue to maximum delay (31 steps = 62ns) while leaving red and green at 0. For the full separation effect, apply different delays to all three planes. Each preset can store a specific "look" — recall it instantly during a performance.

---

### ⭐⭐ Output Skew Adjustment

| What you want | Send | Response |
|---|---|---|
| Set all output skew values (R, G, B) | `{out}*{R}*{G}*{B}*4Oseq↵` | `Oseq{out}•{R}•{G}•{B}↵` |
| Increment one output plane skew | `{out}*{plane}*1Oseq↵` | `Oseq{out}•{R}•{G}•{B}↵` |
| Decrement one output plane skew | `{out}*{plane}*-1Oseq↵` | `Oseq{out}•{R}•{G}•{B}↵` |
| Read output skew values | `{out}*Oseq↵` | `{R}•{G}•{B}↵` |

**Example:** Set output 2 skew to R=0, G=0, B=8ns:
```
2*0*0*4*4Oseq↵  →  Oseq02•00•00•04↵
```

---

### ⭐ Input Pre-peaking (VHS Brightness Overdrive Technique)

| What you want | Send | Response |
|---|---|---|
| Set pre-peak level for input | `{in}*{level}*{out}pek↵` | `Ipe{in}•{level}↵` |
| Increment input peaking by 1 | `{in}*+Ipek↵` | `Ipe{in}•{level}↵` |
| Decrement input peaking by 1 | `{in}*-Ipek↵` | `Ipe{in}•{level}↵` |
| Read input peaking setting | `{in}*Ipek↵` | `{level}↵` |
| Execute auto calibration | `{in}*{out}*0BKADU↵` | multiple responses |

**Pre-peaking range:** 0-255

**Glitch technique note:** Abusing pre-peaking beyond normal calibration range creates VHS-style brightness overdrive. The signal clips and blooms in a distinctly analog way. High values create that characteristic washed-out bright glitch look. Combine with skew for full Joebot aesthetic.

---

### Output Pre-peaking

| What you want | Send | Response |
|---|---|---|
| Set output pre-peaking ON | `{in}*{out}*10pek↵` | `Ope{out}•1↵` |
| Set output pre-peaking OFF | `{in}*{out}*00pek↵` | `Ope{out}•0↵` |
| Read output pre-peaking status | `{out}*10pek↵` | `{status}↵` |

---

### Mutes

| What you want | Send | Response |
|---|---|---|
| Mute output | `{out}*1Z↵` | `Amt{out}•1↵` |
| Unmute output | `{out}*0Z↵` | `Amt{out}•0↵` |
| Mute all outputs | `1*Z↵` | `Amt↵` |
| Unmute all outputs | `0*Z↵` | `Amt↵` |

---

### Lock (Executive) Modes

| What you want | Send | Response |
|---|---|---|
| Lock all front panel functions | `1X↵` | `Exe1↵` |
| Lock advanced front panel functions | `2X↵` | `Exe2↵` |
| Unlock all front panel functions | `0X↵` | `Exe0↵` |
| View lock status | `X↵` | `{status}↵` |

---

### ⭐ System Status Query (Observatory Health Monitoring)

| What you want | Send | Response |
|---|---|---|
| Request full system status | `S↵` | voltages + temp + fan speeds |

**Response includes:**
- Power supply voltages: +3.3V, +5V, +12V, -12V
- Temperature in Fahrenheit
- Fan 1, 2, 3 speeds in RPM

**This is what Observatory uses to show MTPX health in the device card.** One command returns everything needed for the health display.

**Example MTPX Plus 128 response:**
```
+3.28•+4.98•-5.01•+11.52•-12.35•+86.88•03590•03668•03668↵
```
(+3.3V•+5V•-5V•+12V•-12V•temp°F•Fan1RPM•Fan2RPM•Fan3RPM)

---

### Device Information

| What you want | Send | Response |
|---|---|---|
| Query controller firmware version | `Q↵` | `{version}↵` |
| Request part number | `N↵` | `{part}↵` |
| Read IP address | `{n}*I↵` | `{IP}↵` |
| Read MAC address | `{n}*H↵` | `{MAC}↵` |

---

### Resets

**✅ Safe to use in Nexus automation:**

| What you want | Send | Response | Notes |
|---|---|---|---|
| Reset all peaking adjustments | `{in}*ZT↵` | `Zpt↵` | Returns all pre-peaking to default — useful "clean baseline" reset |
| Reset all input and output skew | `{in}*ZK↵` | `Zpk↵` | Zeros all RGB skew — useful "remove glitch effect" reset |

These two are legitimate workflow tools — panic buttons in a good way. "Back to clean signal" in one command.

**⚠️ NEVER call from automation — require explicit user confirmation:**

| What you want | Send | Response | Notes |
|---|---|---|---|
| Reset global presets and names | `{in}*ZG↵` | `Zpg↵` | Destroys all saved presets |
| Reset whole switcher | `{in}*ZXXX↵` | `Zpx↵` | Clears everything |
| Absolute reset | `{in}*Z000↵` | `Zpq↵` | Factory reset + IP reset to 192.168.254.254 |

The Nexus MTPX adapter must require `confirm_reset: true` AND `reset_type: "destructive"` in the payload before executing any of the three dangerous resets. Never call from scenes, patterns, or automation.

---

### Complete MTPX Plus State Snapshot

To capture complete MTPX Plus state for a session snapshot:

```
# Routing — query per output
{out}A↵     → RGB video tie for each output
{out}B↵     → video tie for each output

# Skew — query per input and output
{in}*Iseq↵  → input skew R,G,B for each input
{out}*Oseq↵ → output skew R,G,B for each output

# Pre-peaking — query per input
{in}*Ipek↵  → input peaking level for each input
{out}*10pek↵ → output pre-peaking on/off per output

# System health
S↵          → voltages, temperature, fan speeds

# Device info
Q↵          → firmware version
N↵          → part number
X↵          → executive mode status
```

---

### Nexus Adapter Actions

| Action | Command | Notes |
|---|---|---|
| `tie_input_to_output` | `{in}*{out}!↵` | video+audio |
| `tie_input_rgb_only` | `{in}*{out}&↵` | RGB only |
| `tie_input_video_only` | `{in}*{out}%↵` | video only |
| `tie_input_all_outputs` | `{in}*1↵` | fan to all |
| `recall_preset` | `{n}.↵` | standard Extron |
| `save_preset` | `{n},↵` | standard Extron |
| `read_output_tie` | `{out}A↵` | query routing |
| `set_input_skew` | `{in}*{R}*{G}*{B}*4Iseq↵` | ⭐ glitch technique |
| `increment_input_skew` | `{in}*{plane}*1Iseq↵` | per plane |
| `decrement_input_skew` | `{in}*{plane}*-1Iseq↵` | per plane |
| `query_input_skew` | `{in}*Iseq↵` | read current |
| `set_output_skew` | `{out}*{R}*{G}*{B}*4Oseq↵` | ⭐ output skew |
| `query_output_skew` | `{out}*Oseq↵` | read current |
| `set_input_peaking` | `{in}*{level}*{out}pek↵` | ⭐ glitch technique |
| `increment_input_peaking` | `{in}*+Ipek↵` | +1 step |
| `decrement_input_peaking` | `{in}*-Ipek↵` | -1 step |
| `query_input_peaking` | `{in}*Ipek↵` | read current |
| `set_output_prepeaking` | `{in}*{out}*{0/1}0pek↵` | on/off |
| `mute_output` | `{out}*1Z↵` | mute |
| `unmute_output` | `{out}*0Z↵` | unmute |
| `query_system_status` | `S↵` | ⭐ health monitoring |
| `set_executive_mode` | `{0/1/2}X↵` | lock modes |
| `reset_peaking` | `{in}*ZT↵` | ✅ safe reset |
| `reset_skew` | `{in}*ZK↵` | ✅ safe reset |
| `reset_whole_switcher` | `{in}*ZXXX↵` | ⚠️ confirm required |
| `absolute_reset` | `{in}*Z000↵` | ⚠️⚠️ confirm required |

---

## Device: VSC 500 / 700 / 700D / 900 / 900D
> Extron Scan Converter
> Connection: Serial only — accessed via IPCP/IPL serial passthrough
> Joebot use: Scan conversion for feedback loops, 480i/480p interconversion

### Model Differences

| Feature | VSC 500 | VSC 700 | VSC 700D | VSC 900 | VSC 900D |
|---|---|---|---|---|---|
| Dual input | No | No | No | No | Yes |
| Horizontal filter | No | Yes | Yes | Yes | Yes |
| Flicker filter | No | Yes | Yes | Yes | Yes |
| Input attenuation | No | No | No | Yes | Yes |
| Memory presets | Yes | Yes | Yes | Yes | Yes |

### Input Selection (900D only — dual input)

| What you want | Send | Response |
|---|---|---|
| Select input 1 | `1!↵` | `Chn1↵` |
| Select input 2 | `2!↵` | `Chn2↵` |

### Input Video Type

| What you want | Send | Response |
|---|---|---|
| Set input to RGB | `0\↵` | `Typ 0↵` |
| Set input to YUV | `1\↵` | `Typ 1↵` |
| Query input type | `\↵` | `{value}↵` |

### Memory Presets

| What you want | Send | Response |
|---|---|---|
| Recall preset | `{number}.↵` | `Rpr {number}↵` |
| Save preset | `{number},↵` | `Spr {number}↵` |

### Horizontal Position

| What you want | Send | Response |
|---|---|---|
| Set H position to value | `{value}H↵` | `Hph {value}↵` |
| Shift right one step | `+H↵` | `Hph {value}↵` |
| Shift left one step | `-H↵` | `Hph {value}↵` |
| Query current H position | `H↵` | `{value}↵` |

### Vertical Position

| What you want | Send | Response |
|---|---|---|
| Set V position to value | `{value}/↵` | `Vph {value}↵` |
| Shift up one step | `+/↵` | `Vph {value}↵` |
| Shift down one step | `-/↵` | `Vph {value}↵` |
| Query current V position | `/↵` | `{value}↵` |

### Horizontal Size

| What you want | Send | Response |
|---|---|---|
| Set H size to value | `{value}:↵` | `Hsz {value}↵` |
| Increase H size one step | `+:↵` | `Hsz +↵` |
| Decrease H size one step | `-:↵` | `Hsz -↵` |
| Query current H size | `:↵` | `{value}↵` |

### Vertical Size

| What you want | Send | Response |
|---|---|---|
| Set V size to value | `{value};↵` | `Vsz {value}↵` |
| Increase V size one step | `+;↵` | `Vsz +↵` |
| Decrease V size one step | `-;↵` | `Vsz -↵` |
| Query current V size | `;↵` | `{value}↵` |

### Zoom

| What you want | Send | Response |
|---|---|---|
| Zoom in | `+{↵` | `Zom↵` |
| Zoom out | `-{↵` | `Zom↵` |

### Freeze

| What you want | Send | Response |
|---|---|---|
| Freeze video output | `1F↵` | `Frz1↵` |
| Unfreeze video output | `0F↵` | `Frz0↵` |
| Query freeze status | `F↵` | `Frz{value}↵` |

### Executive Mode

| What you want | Send | Response |
|---|---|---|
| Enable — lock front panel | `1X↵` | `Exe1↵` |
| Disable — allow front panel | `0X↵` | `Exe0↵` |
| Query status | `X↵` | `Exe{value}↵` |

### Test Pattern

| What you want | Send | Response |
|---|---|---|
| Set test pattern | `{value}J↵` | `Tst {value}↵` |
| Query test pattern | `J↵` | `{value}↵` |

### Horizontal Filter / Detail (700, 700D, 900, 900D only)

| What you want | Send | Response |
|---|---|---|
| Set H filter to value | `{value}D↵` | `Dhz {value}↵` |
| Increase one step | `+D↵` | `Dhz {value}↵` |
| Decrease one step | `-D↵` | `Dhz {value}↵` |
| Query current value | `D↵` | `{value}↵` |

### Flicker Filter (700, 700D, 900, 900D only)

| What you want | Send | Response |
|---|---|---|
| Set flicker filter to value | `{value}d↵` | `Dvz {value}↵` |
| Increase one step | `+d↵` | `Dvz {value}↵` |
| Decrease one step | `-d↵` | `Dvz {value}↵` |
| Query current value | `d↵` | `{value}↵` |

### Special Function Commands

#### Encoder Filter / Sharpness

| What you want | Send | Response |
|---|---|---|
| Set encoder filter level (0-3) | `{value}*10#↵` | `Enc {value}↵` |
| Query encoder filter level | `10#↵` | `{value}↵` |

#### Output Video Type

| What you want | Send | Response |
|---|---|---|
| Set to RGBHV (default) | `0*6#↵` | `Tpo 0↵` |
| Set to RGBS | `1*6#↵` | `Tpo 1↵` |
| Set to RGsB | `2*6#↵` | `Tpo 2↵` |
| Set to YUV | `3*6#↵` | `Tpo 3↵` |
| Query current output type | `6#↵` | `{value}↵` |

#### Video Standard

| What you want | Send | Response |
|---|---|---|
| Set to NTSC (default) | `0*14#↵` | `Rte 0↵` |
| Set to PAL | `1*14#↵` | `Rte 1↵` |
| Query current standard | `14#↵` | `{value}↵` |

#### No-Input Pattern

| What you want | Send | Response |
|---|---|---|
| Set to black (default) | `0*13#↵` | `Out 0↵` |
| Set to color bars | `1*13#↵` | `Out 1↵` |
| Query current setting | `13#↵` | `{value}↵` |

#### Input Attenuation (900, 900D only)

| What you want | Send | Response |
|---|---|---|
| Set attenuation value | `{value}*15#↵` | `Attn {value}↵` |
| Query current attenuation | `15#↵` | `{value}↵` |

### Auto Imaging

| What you want | Send | Response |
|---|---|---|
| Auto center and size to fill screen | `55#↵` | `Img↵` |

### Device Information

| What you want | Send | Response |
|---|---|---|
| Query firmware version | `Q↵` | `x.xx↵` |
| Request part number | `N↵` | part number string |
| Request status (700/700D) | `I↵` | `Hrt{value}•Vrt{value}↵` |
| Request status (900/900D) | `I↵` | `Chn{input}•Hrt{value}•Vrt{value}↵` |

### Factory Reset — USE WITH CAUTION ⚠️

| What you want | Send | Response |
|---|---|---|
| Total factory reset | `Esc zXXX↵` | `ZapXXX↵` |

Never call from Nexus automation. Requires explicit `confirm_reset: true` flag.

### Complete VSC State Snapshot

```
\↵      → input video type
H↵      → horizontal position
/↵      → vertical position
:↵      → horizontal size
;↵      → vertical size
F↵      → freeze status
X↵      → executive mode status
J↵      → test pattern
Q↵      → firmware version
6#↵     → output video type
14#↵    → video standard (NTSC/PAL)
13#↵    → no-input pattern
10#↵    → encoder filter level

# Add for 700/700D/900/900D:
D↵      → horizontal filter
d↵      → flicker filter

# Add for 900/900D:
15#↵    → input attenuation

# Add for 900D only:
I↵      → current input source + rates
```

---

## Device: IPCP 505
> Extron IP Link Control Processor
> Connection: HTTP + TCP port 23
> Hostname: ipcp505-1.extron.video
> Joebot use: Serial passthrough to non-networked devices, IR blasting, relay control

### Serial Passthrough via HTTP

```
http://{hostname}/?=cmd{SIS_command}
```

**Example — recall preset 1 on device on serial port 1:**
```
http://ipcp505-1.extron.video/?=cmdW01RS|1.
```

Breaking it down:
- `cmd` — tells IPCP to pass through as serial command
- `W01` — write to serial port 01
- `RS|` — separator
- `1.` — the actual SIS command

### Relay Control via HTTP

```
http://{hostname}/W=1R{relay_number}
```

**Example — trigger relay 1:**
```
http://ipcp505-1.extron.video/W=1R01
```

### Serial Port Layout

| Ports | Type | Pins | Bidirectional | Best use |
|---|---|---|---|---|
| 1-6 | RS-232 | 3-pin | Yes | Devices needing state polling (VSC, video wall controller) |
| 7-8 | RS-232 + flow control | 5-pin Phoenix | Yes | Use 5-pin connectors, leave RTS/CTS pins unconnected |
| 9-16 | Shared with IR | 2-pin | Send only | Fire-and-forget commands only |

**Pro tip:** 5-pin Phoenix connectors are easier to source than 3-pin. Ports 7/8 with 5-pin connectors work identically to 3-pin for standard RS-232 — just leave pins 4 and 5 unconnected.

### IR Control
> TODO — exact EIR trigger command format pending confirmation

---

## Device: IPL T Series
> Extron IP Link Serial Controller
> Models: IPL T S1 (1 port), S2 (2 ports), S4 (4 ports), S6 (6 ports)
> Hostname pattern: iplt-s{model}.extron.video

| Model | Serial Ports | Part Number |
|---|---|---|
| IPL T S1 | 1 | 60-801-01 |
| IPL T S2 | 2 | 60-544-81 |
| IPL T S4 | 4 | 60-544-83 |
| IPL T S6 | 6 | 60-544-84 |

### Serial Passthrough
> TODO — confirm if same HTTP command pattern as IPCP 505

---

## Device: DMS 3600
> Extron Digital Media Switcher
> Connection: TCP port 23
> Hostname: dms.extron.video

### Commands
> TODO — pending manual review

### Known Actions Needed
- `recall_preset` — `{n}.↵` (assumed same pattern)
- `set_video_mute` — mute video output, signal stays synced

---

## Device: MGP 464
> Extron Multi-Graphic Processor
> Connection: TCP port 23
> Hostnames: mgp1.extron.video, mgp2.extron.video, mgp3.extron.video

### Commands
> TODO — pending manual review

### Known Actions Needed
- `recall_preset` — `{n}.↵` (assumed same pattern)
- `set_video_mute` — mute video output

---

## Device: Matrix 12800
> Extron 128x128 Matrix Switcher
> Connection: TCP port 23
> Hostname: mx.extron.video

### Commands
> TODO — pending manual review

### Known Actions Needed
- `recall_preset` — `{n}.↵` (assumed same pattern)
- Route input to output commands — likely same `{in}*{out}!↵` pattern as MTPX Plus

---

## Device: DSC 401A
> Extron RGB/Component to HDMI Scaler
> Joebot owns: 4 units
> Hostname pattern: dsc401a-{n}.extron.video

### Commands
> TODO — pending manual review

---

## Device: USP 405
> Extron Universal Signal Processor
> Hostname: TODO

### Commands
> TODO — pending manual review

---

## Device: DSV 605
> Extron Digital Video Processor
> Hostname: TODO

### Commands
> TODO — pending manual review

---

## Error Codes (Universal)

These error codes appear across Extron devices when a command fails:

| Code | Meaning |
|---|---|
| E01 | Invalid input channel number (out of range) |
| E10 | Invalid command |
| E11 | Invalid preset number (out of range) |
| E12 | Invalid output number (out of range) |
| E13 | Invalid value (out of range) |
| E14 | Invalid command for this configuration |
| E17 | Timeout (caused by direct write of global presets) |
| E21 | Invalid room number |
| E22 | Busy |
| E24 | Privileges violation |
| E25 | Device not present |
| E26 | Maximum number of connections exceeded |
| E27 | Invalid event number |
| E28 | Bad filename / file not found |

The Nexus adapter should parse these and return meaningful error messages rather than raw codes.

---

*Extron SIS Command Reference*
*github.com/joebot94/docs*
*🦖 Joebot Ecosystem*
*Document version 1.1 — March 2026*
