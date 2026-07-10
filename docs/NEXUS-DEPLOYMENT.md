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

## Synology NAS (10.0.0.2)

Same pattern as joebot-lab (which owns port 8080; Nexus takes 8675 — no clash):

1. Copy the repo to the NAS, e.g. `/volume1/docker/nexus-core/`
   (`rsync -a --exclude .venv --exclude data ./ joe@10.0.0.2:/volume1/docker/nexus-core/`).
2. On the NAS: `cd /volume1/docker/nexus-core && sudo docker compose up -d --build`.
3. Verify: `curl -s http://10.0.0.2:8675/api/v1/health` and open
   `http://status.joe.bot:8675/` for the test client.
4. Set `NEXUS_TOKEN` in `docker-compose.yml` before exposing beyond the LAN.
5. Edit devices in `/volume1/docker/nexus-core/data/jbt/device_registry.jbt`,
   then `sudo docker compose restart nexus-core`.

Healthcheck is built into the image; `restart: unless-stopped` +
size-capped json logs are in the compose file.

## Upgrades

```bash
git pull            # or rsync the new tree
docker compose up -d --build
```

`data/` is a volume — registry and event log survive rebuilds.
