# Nexus Core — API

Base URL: `http://<host>:8675`. Interactive docs at `/docs`, OpenAPI schema
at `/openapi.json`. If `NEXUS_TOKEN` is set, send it as `X-Nexus-Token: …`
or `Authorization: Bearer …` (the `/api/v1/health` endpoint stays open for
healthchecks; the WebSocket takes `?token=…`).

## Endpoints

| Method | Path | What |
|---|---|---|
| GET | `/api/v1/health` | service liveness + device counts |
| GET | `/api/v1/devices` | registry with live status |
| GET | `/api/v1/devices/{id}` | one device |
| GET | `/api/v1/devices/{id}/state` | last-known state, each value stamped `{source, updated_at}` |
| GET | `/api/v1/devices/{id}/capabilities` | normalized actions + param schemas + `verified` flags |
| POST | `/api/v1/devices/{id}/probe` | read-only reachability/identity check (safe `Q`) |
| GET | `/api/v1/groups` | logical groups (shape stable, lands M2) |
| POST | `/api/v1/actions` | **the integration path** — dispatch a normalized action |
| POST | `/api/v1/devices/{id}/raw` | guarded diagnostics (`confirm_raw: true` required, logged) |
| GET | `/api/v1/events?limit=100` | recent event history |
| WS | `/api/v1/ws` | live events: `device_status`, `action_result`, `raw_command` |

## The action call

```
POST /api/v1/actions
{ "target": "device.mgp.1", "action": "recall_preset", "parameters": { "preset": 48 } }
```
```json
{
  "ok": true, "target": "device.mgp.1", "action": "recall_preset",
  "parameters": { "preset": 48 }, "response": "Rpr2*048",
  "error": null, "latency_ms": 42, "state": { "preset": 48 }
}
```

`state` contains only what the device ack **confirmed** — an empty `state`
with `ok: true` means "sent and not rejected, but unconfirmed."
Errors: `404` unknown target, `400` unsupported action, `422` bad
parameters, `ok: false` + `error` for device/transport failures
(E-codes are normalized: `"E11: invalid preset number"`).

## Client examples

**curl**
```bash
curl -s localhost:8675/api/v1/actions -H 'Content-Type: application/json' \
  -d '{"target":"device.mgp.1","action":"recall_preset","parameters":{"preset":48}}'
```

**Python**
```python
import httpx

nexus = httpx.Client(base_url="http://10.0.0.2:8675/api/v1")
r = nexus.post("/actions", json={
    "target": "device.mgp.1",
    "action": "recall_preset",
    "parameters": {"preset": 48},
}).json()
assert r["ok"], r["error"]
```

**Swift** (the GlitchBoard M3 connection type, in miniature)
```swift
struct NexusAction: Codable { let target, action: String; let parameters: [String: Int] }
struct NexusResult: Codable { let ok: Bool; let response: String; let latency_ms: Int }

func send(_ action: NexusAction, base: URL) async throws -> NexusResult {
    var req = URLRequest(url: base.appending(path: "/api/v1/actions"))
    req.httpMethod = "POST"
    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    req.httpBody = try JSONEncoder().encode(action)
    let (data, _) = try await URLSession.shared.data(for: req)
    return try JSONDecoder().decode(NexusResult.self, from: data)
}
```

**Browser JS** (live event feed)
```js
const ws = new WebSocket("ws://10.0.0.2:8675/api/v1/ws");
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.type === "event") console.log(d.event.timestamp, d.event.summary);
};

await fetch("http://10.0.0.2:8675/api/v1/actions", {
  method: "POST", headers: {"Content-Type": "application/json"},
  body: JSON.stringify({target: "device.mgp.1", action: "recall_preset",
                        parameters: {preset: 48}}),
});
```

## Device registry

`data/jbt/device_registry.jbt` (`jbt_type: nexus_device_registry`) —
bootstrapped with defaults on first run. Per device: `device_id`, `type`
(adapter key, e.g. `mgp464`), `label`, `host`, `port`, `location`, `notes`,
`enabled`, `simulate`. Edit + restart to apply.
