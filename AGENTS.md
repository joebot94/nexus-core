# AGENTS.md — read this before doing anything in this repo

Multiple agents (Codex, Claude Fable/Opus) work here concurrently. Standing
rules first; the dated directive below is the current marching order.

## Standing rules

1. **Stage files by name. Never `git add -A` or `git add .`** Another agent's
   WIP may be in the tree. One lane per commit.
2. **Live-fire policy (REVISED by Joe, 2026-07-17): live sends are ALLOWED.**
   Nothing in the glitch rack is harmed by normal commands (recalls, routes,
   skew, freeze, blank); Joe live-verified preset recall 4 ways. Two rails
   remain: (a) **destructive resets stay confirm-gated** (ZG/Z000/zap can
   wipe saved presets and device configs — never automated); (b) unattended
   runs still prefer dry-run, simply because nobody can see the wall.
3. **Do not redeploy to the NAS on your own** — redeploy is coordinated with
   Joe. (The NAS currently runs 0.20.0; repo is 0.21.0.)
4. Keep tests green; new endpoints/generators need tests. Doc-only wire
   strings ship `verified=False` until bench-confirmed (truth hierarchy:
   live-verified code > deployed lab code > docs).

## CURRENT DIRECTIVE — 2026-07-17 (from Joe, via Claude Fable)

- **TextWall lane is COMMITTED** (075d76a, v0.20.0 — matches the NAS deploy).
  The 07-13 "commit the TextWall lane" directive is fulfilled; tree is clean.
- **v0.21.0 shipped at Joe's direct request:** `tie_many` quick-multiple-tie
  on DMS 3600 + Matrix 12800 (doc-only wire, `verified=False`), `chain_ties`
  option on the videowall baseline generator, and
  `scripts/bench_rate_sweep.py` (operator-graded switching-rate sweeps).
  See docs/NEXUS-STATUS.md 2026-07-17 and **docs/BENCH-NIGHT.md** — the
  latter is the single checklist for everything bench-gated.
- **Open follow-ups, unblocked for whoever picks them up** (tests + status
  ledger entry required, stage by name):
  - SMX + MGP chained-command variants — ONLY after someone reads the
    manuals' SIS chainability notes or bench-tests the wires; do not invent
    wire strings.
  - An `overdrive` flag alongside `clamp_rate` in `nexus/videowall.py`
    (deliberately exceeding a mechanism's clean rate as a stutter effect) —
    worth building only after bench numbers replace the MECHANISMS
    placeholders.
- **Still held:** NAS redeploy (with Joe), destructive-reset automation
  (never), GlitchBoard-side lanes (see that repo's AGENTS.md — Composer
  Phase 4b + UX pass await Joe's review; Phase 5 after).
