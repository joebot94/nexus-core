# Nexus — Claude Code Session Prompt v1.0
> Paste this entire prompt at the start of a Claude Code or Codex session
> Goal: Get basic Nexus Python server running and talking to a Swift test client

---

## Context

I am building an ecosystem of apps for a glitch art studio called the Joebot Ecosystem. The central piece is a Python server called **Nexus** that acts as the single coordination point for all apps and devices. No app talks directly to another app — everything goes through Nexus.

The full architecture is documented at:
`https://raw.githubusercontent.com/joebot94/docs/main/Nexus_Architecture.md`

Please read that document before starting.

---

## What I need built today

Build a basic but real working skeleton of the Nexus server. Not a toy hello world — a properly structured foundation that we can build on without rewriting.

### Core requirements for this session:

**1. WebSocket server**
- Python 3.11+
- asyncio + websockets library
- Listen on 0.0.0.0 port 8765
- Accept multiple simultaneous client connections
- Log every connection and disconnection with timestamp

**2. Client registration**
- Accept a `register` message from connecting clients
- Store client info in a registry — client_id, client_type, version, capabilities
- Respond with `registered` confirmation message
- Log registration events

**3. Heartbeat monitoring**
- Accept `heartbeat` messages from clients
- Track last seen timestamp per client
- If a client misses 3 consecutive heartbeats (15 seconds) mark it offline
- Retain last known state when client goes offline
- Log offline/online transitions

**4. State store**
- Accept `state_update` messages from clients
- Store current state per client_id
- Accept `query` messages — return current state for requested client_id
- State persists in memory even when client goes offline

**5. Basic intent routing**
- Accept `intent` messages with a targets array
- Fan out the intent payload to all listed target clients simultaneously
- Log routing events

**6. Event logging**
- Central log bus
- Every significant event gets logged with timestamp, level, subsystem, message
- Broadcast log events to any connected client that has registered as a monitor type
- Print to console as well

**7. Message envelope**
All messages use this standard format:
```json
{
  "id": "msg_001",
  "type": "message_type_here",
  "source": "client_id_here",
  "payload": {}
}
```

All message models must use **Pydantic v2**.

---

## Folder structure to create

```
nexus/
├── main.py
├── requirements.txt
├── README.md
├── config/
│   └── settings.py
├── core/
│   ├── registry.py
│   ├── state_store.py
│   ├── heartbeat.py
│   └── log_bus.py
├── api/
│   ├── models.py
│   ├── websocket_server.py
│   └── handlers.py
└── test_client.py
```

---

## Known message types to implement

### Incoming (client → Nexus)

```json
{ "type": "register", "payload": {
    "client_id": "dirtymixer_v1",
    "client_type": "dirtymixer",
    "version": "1.0.0",
    "capabilities": ["presets", "automation"]
}}

{ "type": "heartbeat", "payload": {
    "client_id": "dirtymixer_v1",
    "timestamp": 1234567890
}}

{ "type": "state_update", "payload": {
    "client_id": "dirtymixer_v1",
    "state": { "connected_to_board": true, "active_preset": "Preset 12" }
}}

{ "type": "query", "payload": {
    "target_client_id": "dirtymixer_v1"
}}

{ "type": "intent", "payload": {
    "targets": ["dirtymixer_v1", "textwall_v1"],
    "action": "recall_preset",
    "params": { "preset_id": 12 },
    "sync": true
}}
```

### Outgoing (Nexus → client)

```json
{ "type": "registered", "payload": { "status": "ok", "client_id": "dirtymixer_v1" }}
{ "type": "state_response", "payload": { "client_id": "...", "state": {} }}
{ "type": "command", "payload": { "action": "...", "params": {} }}
{ "type": "client_offline", "payload": { "client_id": "...", "last_seen": 123 }}
{ "type": "client_online", "payload": { "client_id": "..." }}
{ "type": "log_event", "payload": { "level": "info", "subsystem": "registry", "message": "..." }}
{ "type": "error", "payload": { "message": "..." }}
```

---

## Test client requirements

Build a `test_client.py` that:
- Connects to Nexus on localhost 8765
- Sends a register message as `test_client_01` with type `test`
- Sends heartbeats every 5 seconds
- Sends a state update every 10 seconds with fake state data
- Sends a test intent message every 30 seconds
- Prints everything it receives from Nexus
- Runs in a loop until killed with Ctrl+C

This lets me verify the server is working without needing real apps connected.

---

## Code quality requirements

- Type hints throughout
- Pydantic v2 for all message models
- Small focused modules — no giant files
- Clear docstrings on all classes and functions
- Graceful error handling — a bad message from one client should never crash the server
- Explicit TODO comments where things are stubbed
- The server must keep running even if a client sends garbage

---

## What success looks like

When this session is done I should be able to:

1. Run `python main.py` and see Nexus start up on port 8765
2. Run `python test_client.py` in another terminal
3. See the client register in Nexus logs
4. See heartbeats being tracked
5. See state updates being stored
6. See intent messages being routed
7. Kill the test client and see Nexus detect it as offline after 15 seconds
8. Restart the test client and see Nexus detect it as back online

That's the proof of concept. Everything else builds on this working.

---

## Capability Discovery

Nexus must support capability discovery so apps like the DAW can ask "what can this device do" and build their UI dynamically from the response.

### How it works

DAW or any client sends:
```json
{
  "type": "capabilities.query",
  "payload": {
    "target_client_id": "dirtymixer_v1"
  }
}
```

Nexus forwards to DirtyMixerApp which responds:
```json
{
  "type": "capabilities.response",
  "payload": {
    "client_id": "dirtymixer_v1",
    "capabilities": {
      "channels": 9,
      "channel_params": ["mix", "input_a", "input_b"],
      "mix_range": [0, 255],
      "presets": 24,
      "modes": ["manual", "random", "automation"],
      "grouping": true
    }
  }
}
```

Nexus passes that back to the requesting client.

The requesting app — DAW, Observatory, whatever — builds its UI entirely from what came back. No hardcoding of device capabilities anywhere except in the device's own app.

### Why this matters

- DAW shows exactly 9 channel boxes because dirty mixer said 9 — not because it was hardcoded
- Upgrade to 16 channel board — DAW shows 16 boxes automatically
- New device joins ecosystem — any app can discover what it does immediately
- Zero app updates needed when hardware changes

### Add these message types:

| Type | Direction | Description |
|---|---|---|
| `capabilities.query` | client → Nexus | Ask what a specific client can do |
| `capabilities.request` | Nexus → client | Nexus forwards query to target client |
| `capabilities.response` | client → Nexus | Target client responds with its capabilities |
| `capabilities.result` | Nexus → client | Nexus forwards capabilities back to requester |

Store capabilities in state store when received so Nexus can answer capability queries from cache without always forwarding to the device.

---

## Notes

- Do NOT build a GUI for Nexus — it runs headless
- Do NOT build Extron adapters yet — that's a future session
- Do NOT build scene/preset management yet — future session
- Focus entirely on the WebSocket layer and core message handling
- The server must be able to run even with zero clients connected
- DO implement capability discovery — it's needed by the DAW app and Observatory

---

## Requirements.txt should include at minimum

```
websockets>=12.0
pydantic>=2.0
asyncio
```

---

*Nexus skeleton build session*
*github.com/joebot94/nexus*
*Part of the Joebot Ecosystem*
