# Bench Night — everything gated on Joe standing at the rack

One checklist for the next hands-on session. Each item says what to run, what
to watch, and where the answer gets written down. Order is chosen so early
answers unblock later items. Live-firing is fine (policy revised 2026-07-17);
only destructive resets (ZG/Z000/zap) stay off the table.

Prereqs: laptop on the rack LAN, this repo, devices powered. Nothing here
needs the NAS Nexus — the sweep tool talks straight TCP.

## 1. Quick multiple tie — does the wire work? (~10 min)

The new `tie_many` action assumes `in1*out1*in2*out2...!` → `Qik` from the
SIS reference. Confirm per device with a bare telnet (`nc <host> 23`):

- **DMS 3600** (10.0.0.13): send `1*1*2*2!` — expect `Qik`. Watch: do both
  outputs switch together (one blink) or visibly one-after-another?
- **Matrix 12800** (10.0.0.12): same test, composite outputs.
- **SMX** (10.0.0.11): try the plane-prefixed guesses `00*1*1*2*2&` and the
  Esc form — or just read its manual's SIS table first. Whatever works,
  record the exact wire; the adapter gets it afterward.
- **MGP 464** (10.0.0.63): read the manual's SIS table for `in*win!`
  chainability (usually a "can be chained" column at the top of the table).
- Also probe the line-length ceiling on the DMS: a 16-pair and a 32-pair
  chained tie — accepted or E-code?

Write results → flip `verified=True` on `tie_many` (or fix the wire), adjust
the 32-pair cap, add the SMX/MGP variants if they exist.

## 2. Rate sweeps — where clean ends, cool lives, and broken begins

`scripts/bench_rate_sweep.py` runs the sweep; you watch and grade each stage
(clean / glitchy-cool / broken). One JSON report per run. Do these four:

```bash
# a. DVI re-handshake ceiling — THE big unknown (MECHANISMS placeholder: 12 Hz)
scripts/bench_rate_sweep.py --host 10.0.0.13 --mode dms-tie --a 1 --b 2 --target 5

# b. MGP input-remap — re-confirm the one real number (~15 Hz)
scripts/bench_rate_sweep.py --host 10.0.0.63 --mode mgp-input --a 3 --b 4 --target 1

# c. MGP window/preset move (placeholder: 4 Hz)
scripts/bench_rate_sweep.py --host 10.0.0.63 --mode mgp-preset --a 48 --b 52

# d. Composite route on the 12800 (placeholder: 12 Hz)
scripts/bench_rate_sweep.py --host 10.0.0.12 --mode dms-tie --a 1 --b 2 --target 5
```

Write `max_clean_hz` into `MECHANISMS` in `nexus/videowall.py` and flip
`verified=True`. Keep the reports in `docs/bench-reports/`. The glitchy-cool
band is a FEATURE: it becomes the "overdrive" stutter range once an
overdrive flag exists (deliberately over-driving a mechanism past clean as
an effect — currently `clamp_rate` hard-caps instead).

## 3. Standing bench backlog (older gated items, still open)

- **MTPX lane count:** how many concurrent sockets does a real MTPX accept?
  (lanes transport defaults to 10, ≤32 — tune from reality.)
- **MTPX skewable-input set on the 128:** which inputs actually take
  `W…Iseq` (4-vs-2 VGA question from the topology pass).
- **SMX blank dispatch** (GlitchBoard's blank-via-SMX path is bench-gated).
- **DMS per-output mute wire** (in the manual; adapter has no wire yet).
- **IPCP EIR scan** (`1I`/`2I`, `ESC LF CR` file list) so IR cues
  (wall controller source modes!) become fireable.
- **MTPX preset save/recall round-trip** (`{N},` save) — do presets store
  skew? Loopback max-pass signal ceiling?
- **First composed scene live-fire:** generate a chaos-scene from Nexus,
  recall it, watch the wall do "one quadrant crazy, rest clean" for real.

## 4. When the DMS + 4 more MGPs land in the glitch room

That's the moment the 3×3/4×4 wall stops being theoretical: run the full
baseline → scramble → return-to-baseline cycle from the API (or GlitchBoard
once its wall-cue fire path is wired), with `chain_ties: true` if item 1
verified. This is the "it DOES actually work / ohh fuck we need to fix it"
moment — either way, it's the cheapest it will ever be to find out.
