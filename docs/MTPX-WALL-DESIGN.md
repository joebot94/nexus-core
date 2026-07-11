# MTPX Wall — Cascade & Baseline Scene Design

> The "figure it out once" document (Joe's 2026-07-11 brain dump, item B).
> Everything here is derivable logic + verified protocol facts; the parts that
> still need a bench pass are collected at the bottom. Executable version of
> this logic: `nexus/wallplan.py` (pure, tested, fires nothing).

---

## 1. The physics of the trick

Skew on an MTPX Plus is a **per-input** setting: `W{in}*{r}*{g}*{b}Iseq`,
each channel 0–31 (live-verified). A signal picks up an input's skew every
time it passes through that input. One pass caps at 31 px per channel.

**The cascade**: patch an output back into another *skewable* input with a
short cable, tie the signal through it, and the signal gets skewed again.
Total skew = 31 × (number of passes). The cables are physical and static —
set up once. The **ties are electronic** — which means:

> **Lanes are formed by ties, not by cables.** The loopback patch is a fixed
> menu of possible hops; the current tie set decides which hops a signal
> actually takes. Change the ties → the wall re-forms. Save the tie set as a
> unit preset → the whole lane structure is recallable with one `{N}.`

That's the reason "set up ties and presets, save them, recall them" is the
foundation: **a unit preset IS a lane configuration.**

## 2. Port budget — why a 128 carries 3 (maybe 4) sources

MTPX Plus 128 = 12 in × 8 out; **skew only works on inputs 5–12** (1–4 are
VGA/analog pass-through). So per unit: **8 skewable inputs, 8 outputs.**

A lane with *p* skew passes consumes:
- *p* skewable inputs (source enters on one, each loopback re-enters on one)
- *p* outputs (p−1 feeding loopback cables, 1 final out to downstream)
- p−1 physical loopback cables

| Layout on one 128 | Skewable ins | Outs | Max skew/channel | Spare |
|---|---|---|---|---|
| 3 lanes × 2-pass | 6/8 | 6/8 | 62 px | 2 in, 2 out |
| 3 × 2-pass + 1 × 2-pass | 8/8 | 8/8 | 62 px | none |
| 3 × 2-pass + 1 × 1-pass | 7/8 | 7/8 | 62 / 31 px | 1 in, 1 out |
| 1 monster lane × 8-pass | 8/8 | 8/8 | **248 px** | none |

Joe's estimate ("each can handle 3 signals, maybe one does a 4th") is the
middle rows. The 4 VGA inputs are free bonus routes on every unit — clean
bypass paths, SMX VGA-card returns, or sacrificial chaos feeds (they route
fine, they just can't skew).

**Wall math**: 5 × 128 → 4 units × 3 slots + 1 unit × 4 slots = **16 slots**.

## 3. Naming & addressing

- Units: `mtpx1` … `mtpx5`, DNS `mtpxN.extron.video` (registry `host` field —
  IPs currently UNCONFIRMED, units powered off; resolve on power-up).
- Wall slots: `r{row}c{col}` in the 4×4 logical wall. The registry/plan maps
  slot → (unit, lane), so a unit **knows its place in the wall**.
- A lane is addressed `mtpx3/L2` (unit, lane index) internally; clients only
  ever speak slots.

## 4. The full signal chain (baseline)

```
source ──▶ mtpxN skewable in ──tie──▶ out ──cable──▶ skewable in ──tie──▶ final out
                 (skew pass 1)              (skew pass 2)                    │
                                                                            ▼
                                                     Matrix 12800 in (1–16, one per slot)
                                                                            │ tie
                                                                            ▼
                                                     12800 out k ──▶ MGP⌈k/4⌉ input, window
                                                                            ▼
                                                                     wall quadrant r,c
```

- Each MGP 464 takes 4 inputs / 4 windows = **one MGP per 4 slots**; the full
  16-slot wall needs 4 MGPs (today: 1 racked → run a 4-slot subset; the plan
  scales without redesign — this is the Multi-MGP Wall FX Chase's plumbing).
- DMS 3600 / SMX sit as alternate paths off the 12800 (SMX's spare VGA card
  can take mtpx VGA-input returns). They join the scene as route presets.

## 5. The baseline scene ("normal")

One recallable, cross-device known-good state — the reference point all
fuckery deviates from and returns to:

| Device | Baseline content | Mechanism |
|---|---|---|
| mtpx1–5 | lane tie sets + all skews 0 | unit preset `{N}.` recall + skew-0 batch |
| Matrix 12800 | slot k → out k identity routing | preset recall (verified) |
| DMS 3600 / SMX | default patch, no scramble | preset recall |
| MGP(s) | canonical layout, no blank/freeze | `2*NN.` layout preset (verified) |

Scene = an ordered list of Nexus actions — exactly what `/groups` + the
coordination plane's *scenes* were already slated to carry (NEXUS-NEXT).
Baseline is scene #1. **Chaos modes are deltas layered on it:**

1. **SMX scramble** — routing chaos upstream, MGP stays clean.
2. **MGP fuckery** — blank/freeze/layout chases downstream, routing stays clean.
3. **12800 scramble** — slots land on wrong quadrants.
4. **Total chaos** — all of the above + skew scenes. One "baseline" recall
   walks it all back.

## 6. What changed in code (v0.5.0)

- `nexus/wallplan.py` — pure planner: give it unit specs + per-slot pass
  counts, it allocates ports, validates budgets, and emits (a) the physical
  loopback patch list (cable-by-cable, for rack setup), (b) per-unit tie
  wires, (c) 12800 tie wires, (d) per-lane skew-input lists with
  `distribute_skew()` to split a big total across passes. Deterministic,
  never fires; tests in `tests/test_wallplan.py`.
- MTPX adapter grew `save_preset` (`{N},` — **verified=false**, doc-only).
  Named explicitly so nobody ever "fixes" recall into save again (the USP
  `{n},` bug). Recall stays `{N}.`.

## 7. Bench-verify before trusting (in order)

1. **MTPX tie** `{in}*{out}!` — verified=false. Everything here rests on it.
2. **Preset save `{N},` / recall `{N}.` round-trip** — and *what a preset
   stores*: ties certainly; whether skew values are stored per-preset or
   persist per-input independently changes scene design (baseline currently
   assumes skew is NOT in the preset → explicit skew-0 batch on recall).
3. **Loopback signal integrity** — how many passes before the picture
   degrades? (MTPX is UTP gear; each pass re-equalizes. 248 px of skew may be
   gloriously ugly — that's fine — but sync must survive.) Find the real
   max-pass ceiling per unit.
4. **Skew stacking is additive** across passes as assumed (31+31 = visually 62).
5. IPs / DNS for mtpx1–5 on power-up (.15/.16 vs .61/.172/.173 conflict).

## 8. Order of operations to make it real

1. Bench pass (above) with operator — one unit, one 2-pass lane.
2. Registry entries for mtpx1–5 with wall-position metadata.
3. Baseline scene as the first `/groups`/scene implementation.
4. GlitchBoard: point `MTPXTopology` profiles at the planner's output format
   so the Swift editor and Nexus share one truth.
5. Graphical wall view (drag a source to a slot → planner re-resolves).
