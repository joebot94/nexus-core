# Adding a Device Without Fanfare

The whole point of the adapter model: a new device should cost **one registry
entry** if its family is known, and **one small file** if it isn't.

## Level 0 — it's an Extron box (60 seconds, no code)

Every Extron device speaks the universal SIS patterns, so the generic
`extron_sis` type works immediately for preset recall + identity:

1. Edit `data/jbt/device_registry.jbt`, add:
   ```json
   {
     "device_id": "device.dxp.1",
     "type": "extron_sis",
     "label": "DXP 88",
     "host": "10.0.0.14",
     "port": 23,
     "enabled": true
   }
   ```
2. `curl -X POST localhost:8675/api/v1/registry/reload`
3. Done. The device appears in `/devices` and the web client with Probe +
   Recall Preset; malformed entries are skipped with a warning, never a crash.

Add `"password": "..."` if the box prompts on connect (the transport answers
password/login prompts automatically, defaulting to admin/admin like the lab).
Add `"simulate": true` to develop against it before it's powered.

## Level 1 — it needs model-specific commands (one small file)

Subclass the closest family base and override only what differs. The SMX is
the canonical example — everything is inherited except the two things the SMX
does differently:

```python
class SMXAdapter(ExtronSISAdapter):
    device_type = "smx"
    actions = {...}                      # declare its normalized actions

    async def do_recall_preset(self, preset):   # SMX rejects universal `N.`
        return await self.send(f"Rpr{preset:02d}")
```

Checklist:
1. `nexus/adapters/<model>.py` — subclass, `actions` dict (mark doc-derived
   commands `verified=False`), `do_<action>` handlers, and a `Simulator`
   so sim mode + tests work before hardware exists.
2. Register it in `ADAPTER_TYPES` (`nexus/adapters/__init__.py`) — one line.
3. Sim tests in `tests/` (copy the pattern in `test_m2_adapters.py`).
4. Registry entry + reload.

Nothing else changes: the API, web client (buttons come from
`/capabilities`), state store, and event stream all pick the device up
automatically. GlitchBoard reaches it by setting `nexusDeviceID`.

## Level 2 — new protocol family (new base + transport)

For non-SIS devices (MIDI, OSC, HTTP-only, serial-behind-IPCP), write a new
family base implementing `DeviceAdapter` and, if needed, a new transport with
the same `exchange()` shape. The MTPX/IPCP adapters (M2 continuation) and the
DSC 401's SWIS-over-WebSocket are the upcoming examples.

## Where protocol truth comes from (in order)

1. Live-verified code (GlitchBoard July 2026 sessions, this repo's live log)
2. Deployed joebot-lab modules (`sis.py`, `*_control.py`)
3. March 2026 docs (`docs/reference/Extron_SIS_Reference.md`) — mark these
   `verified=False` until bench-tested

## Rules that keep it safe

- Actions that change state parse the device ack before claiming confirmed
  state; queries stamp `source: "query"`.
- Destructive commands (resets, preset saves that overwrite) need explicit
  confirm flags and never fire from automation.
- Never fire mutating commands at the wall without an operator watching.
