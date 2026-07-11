# Nexus Core — Deployment

## Local (dev, any platform)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m nexus
```

http://localhost:8675/ — registry bootstraps to `data/jbt/device_registry.jbt`
on first run. Environment knobs: `NEXUS_HOST`, `NEXUS_PORT`, `NEXUS_DATA_DIR`,
`NEXUS_REGISTRY`, `NEXUS_TOKEN`, `NEXUS_SIMULATE=1`.

No hardware nearby? `NEXUS_SIMULATE=1 .venv/bin/python -m nexus` fakes every
device through the same adapter path.

## Docker

```bash
docker compose up -d --build
docker compose logs -f nexus-core
curl -s localhost:8675/api/v1/health
```

`network_mode: host` so the container reaches rack devices on 10.0.0.x
directly (same pattern as joebot-lab). `./data` holds the registry and the
rolling event log — **that directory is the backup unit**: copy it off, and
restoring it onto a fresh checkout restores the deployment.

## NAS (10.0.0.2 / nas.joe.bot) — DEPLOYED 2026-07-10

Live at **http://nas.joe.bot:8675/** (joebot-lab keeps 8080 — no clash).
The box is aarch64 with Docker 26 + Compose v2.26; user `joe` is in the
`docker` group, so no sudo needed. **The NAS's rsync is a restricted
daemon wrapper ("invalid path") — deploy with tar-over-ssh instead:**

```bash
# from the repo root on the Mac — this IS the deploy script
tar czf - --exclude .venv --exclude data --exclude .git \
    --exclude __pycache__ --exclude .pytest_cache . \
  | ssh joe@10.0.0.2 'cd /volume1/docker/nexus-core && tar xzf -'
ssh joe@10.0.0.2 'cd /volume1/docker/nexus-core && docker compose up -d --build'
curl -s http://nas.joe.bot:8675/api/v1/health
```

First-time only: `ssh joe@10.0.0.2 'mkdir /volume1/docker/nexus-core'`.

- Registry lives at `/volume1/docker/nexus-core/data/jbt/device_registry.jbt`
  (bootstrapped on first start). Edit it, then
  `curl -X POST http://nas.joe.bot:8675/api/v1/registry/reload` — no restart.
- Point clients (GlitchBoard's "Nexus API" devices, the iPad) at
  Host `nas.joe.bot`, Port `8675`.
- Set `NEXUS_TOKEN` in `docker-compose.yml` before exposing beyond the LAN.
- Nexus keeps a warm in-memory DMS snapshot for fast clients: routes and Lab
  telemetry refresh every `NEXUS_CACHE_POLL_SECONDS` (default 10), while names
  refresh every `NEXUS_NAME_CACHE_SECONDS` (default 300). This is read-only;
  `data/` remains the persistent registry/log unit and cache is rebuilt after
  restart.
- Healthcheck is built into the image; `restart: unless-stopped` +
  size-capped json logs are in the compose file, so it survives NAS reboots.

## Upgrades

Re-run the tar + `docker compose up -d --build` pair above.
`data/` is outside the image — registry and event log survive rebuilds.
