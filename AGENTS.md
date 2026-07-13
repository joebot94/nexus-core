# AGENTS.md — read this before doing anything in this repo

Multiple agents (Codex, Claude Fable/Opus) work here concurrently. Standing
rules first; the dated directive below is the current marching order.

## Standing rules

1. **Stage files by name. Never `git add -A` or `git add .`** Another agent's
   WIP may be in the tree. One lane per commit.
2. **Never live-fire mutating hardware commands unless Joe is present and
   watching.** Dry-run everything.
3. The NAS deployment (nas.joe.bot:8675) runs an older version than this repo.
   **Do not redeploy to the NAS on your own** — redeploy is coordinated with
   Joe present.
4. Keep tests green; new endpoints/generators need tests.

## CURRENT DIRECTIVE — 2026-07-13 (from Joe, via Claude Fable)

The working tree currently has **uncommitted TextWall relay work**
(`nexus/textwall.py`, `tests/test_textwall_relay.py`, relay routes in
`nexus/api/routes.py`/`models.py`/`config.py`, docker-compose changes).

- If TextWall is your lane: **finish it, get `tests/test_textwall_relay.py`
  passing, and commit it as its own commit(s), staged by name.** Do not let
  this WIP get swept into an unrelated commit or sit dirty across sessions.
- If it is not your lane: leave those files untouched.

**Do NOT start** new wall-planner/videowall features, SMX adapters, or any
deploy work — GlitchBoard's Wall Composer Phases 1–3 are awaiting Joe's
review, and the next Nexus-side architecture (latches resolver, SMX signal
paths) gets a Fable design pass first.
