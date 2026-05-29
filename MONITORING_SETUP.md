# NAS Bot — Monitoring & Alerting Setup Guide

This guide covers everything to configure **before** (and when) you run the bot so background monitoring and Telegram alerts work on your NAS.

## Quick checklist

| Requirement | Why |
|-------------|-----|
| `TELEGRAM_TOKEN` + `ALLOWED_USER_IDS` | Alerts are sent as Telegram DMs |
| `OPENAI_API_KEY` | Optional; enables **AI assist** button on DOWN alerts |
| Docker socket mounted | Container monitors, image-update alerts, `/docker` |
| `ping` in container/host | Ping monitors |
| `tailscale` CLI (optional) | Built-in Tailscale monitor |
| `cloudflared` process or systemd (optional) | Built-in Cloudflare Tunnel monitor |
| `HOST_EXEC_MODE=nsenter` or `ssh` (optional) | systemd monitors, host reboot, SMART on NAS |
| `CRON_NOTIFY_SECRET` (optional) | Push heartbeats from cron / Uptime Kuma scripts |

---

## 1. Environment file

Copy and edit:

```bash
cp .env.example .env
```

### Minimum for alerting

```env
TELEGRAM_TOKEN=...
ALLOWED_USER_IDS=123456789
OPENAI_API_KEY=sk-...

UPTIME_MONITORING_ENABLED=true
```

### Recommended NAS / Docker compose

```env
# Host access (OpenMediaVault NAS)
HOST_EXEC_MODE=nsenter
HOST_NSENTER_PID=1

# Monitoring intervals
HEALTH_CHECK_INTERVAL=5
UPTIME_TICK_SECONDS=30

# Built-in probes (created on first start)
UPTIME_BUILTIN_INTERNET=true
UPTIME_BUILTIN_TAILSCALE=true
UPTIME_BUILTIN_CLOUDFLARED=true
NETWORK_TAILSCALE_CLI=true

# Cloudflare tunnel check mode: process | systemd | tcp:127.0.0.1:7844
UPTIME_CLOUDFLARED_TARGET=process

# Alerts
UPTIME_REBOOT_ALERT_ENABLED=true
UPTIME_DOCKER_IMAGE_ALERTS=true
UPTIME_AUTO_DISCOVER_DOCKER=true
MONITOR_SYSTEMD_UNITS=docker,smbd,nginx

# AI on DOWN alerts: default off — tap "AI assist" on the alert (uses API credits)
UPTIME_AI_ON_INCIDENT=false
UPTIME_AI_BUTTON=true
AUTOTROUBLESHOOT_ENABLED=false

# Escalation: notify at 1st, 3rd, 10th consecutive failure
UPTIME_ESCALATION_THRESHOLDS=1,3,10
```

### Running outside a real NAS (dev VM)

```env
HOST_EXEC_MODE=none
UPTIME_BUILTIN_CLOUDFLARED=false
UPTIME_BUILTIN_TAILSCALE=false
```

---

## 2. Docker / Compose prerequisites

If the bot runs **in a container**, mount:

```yaml
services:
  nas-bot:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./data:/app/data
    # For nsenter host checks (typical OMV setup):
    pid: host
    privileged: true
    cap_add:
      - SYS_PTRACE
```

Install in the image (or host) if you use built-in monitors:

- `iputils-ping` or `ping` — ping monitors  
- `tailscale` — Tailscale monitor (`NETWORK_TAILSCALE_CLI=true`)  
- `cloudflared` — Cloudflare tunnel monitor (process or systemd on host)

For **process monitors** (`/proc`), the bot must see the host PID namespace (`pid: host` or run on host directly).

---

## 3. First start (what happens automatically)

On `python bot.py` startup:

1. SQLite tables for monitors, heartbeats, incidents, groups, image snapshots  
2. **Built-in monitors** (if missing):  
   - `internet-https`, `internet-ping`, `dns-resolve`  
   - `systemd-<unit>` for each `MONITOR_SYSTEMD_UNITS` entry  
   - `tailscale-mesh` (if Tailscale enabled)  
   - `cloudflare-tunnel` (if Cloudflared enabled)  
3. **Docker auto-discovery** — running containers → `docker-<name>` monitors  
4. **Background jobs**: health loop + uptime engine + weekly report  

No manual `/monitor_add` required for basics; add custom URLs/services as needed.

---

## 4. Monitor types reference

| Type | Target example | Notes |
|------|----------------|-------|
| `http` / `https` | `https://jellyfin.local:8096` | Status 2xx/3xx OK |
| `tcp` | `192.168.1.10:5432` | TCP connect |
| `ping` | `1.1.1.1` | ICMP (needs ping binary) |
| `dns` | `cloudflare.com` | Resolves hostname |
| `ssl` | `example.com:443` | Keyword field = warn days (default 14) |
| `keyword` | `https://site/` + keyword in monitor config | HTTP body must contain keyword |
| `docker` | `jellyfin` | Container running + healthy |
| `process` | `nginx` or `cmd:immich` or `pid:1234` | Reads `/proc` |
| `systemd` | `docker` | Needs `HOST_EXEC_MODE` |
| `tailscale` | `docker:tailscale` | `docker exec` + `tailscale status --json` (use when TS runs in Docker) |
| `tailscale` | `docker:auto` | Find running container with *tailscale* in the name |
| `tailscale` | `cli` / `online` | Host `tailscale` binary in PATH |
| `tailscale` | `container:tailscale` | Only check container is running |
| `cloudflared` | `process` / `systemd` / `tcp:127.0.0.1:7844` | Tunnel daemon |
| `push` | `heartbeat` | Use `/monitor_push` for token |

### Examples

```text
/monitor_add jellyfin https https://127.0.0.1:8096 120
/monitor_add postgres-tcp tcp 127.0.0.1:5432 60
/monitor_add immich-worker process cmd:immich-server 120
/monitor_dep postgres-tcp immich-http
/monitor_tag jellyfin media,public
/monitor_stats jellyfin
```

---

## 5. Groups, tags, escalation

- **Groups**: `/monitor_group_create media` → `/monitor_group_add media jellyfin`  
- **Tags**: `/monitor_tag jellyfin media,public` — used for silences and filtering  
- **Escalation**: repeated failures re-alert at thresholds `1,3,10` (env: `UPTIME_ESCALATION_THRESHOLDS`)  
- **Dependencies**: `/monitor_dep parent child` — suppress child DOWN when parent is down  

---

## 6. Push monitors (cron / scripts)

Create a push monitor:

```text
/monitor_push backup-job 300
```

Bot returns a token. Ping it from cron on the NAS:

```bash
# Via cron notify server (same port as CRON_NOTIFY_PORT, default 18765)
curl -fsS "http://127.0.0.1:18765/push/YOUR_TOKEN"

# Or POST to /notify for job status (needs CRON_NOTIFY_SECRET in JSON)
```

Set in `.env`:

```env
CRON_NOTIFY_SECRET=long-random-string-at-least-24-chars
CRON_NOTIFY_PORT=18765
```

Restart the bot after setting the secret. In logs you should see: `Cron notify HTTP listening on 127.0.0.1:18765`.

### Troubleshooting “Could not connect to 127.0.0.1:18765”

The HTTP hook runs **inside** the bot container, not on the NAS host by default.

| Symptom | Fix |
|--------|-----|
| `curl: (7) Failed to connect` from host script | Pull latest `scripts/notify_watchtower.sh` (auto uses `docker exec`). For host port: `docker compose up -d --force-recreate` (not just `restart`) |
| `curl: (56) Connection reset by peer` on host `:18765/health` | Bot was listening on `127.0.0.1` *inside* the container only — set `CRON_NOTIFY_BIND=0.0.0.0` in compose (default in repo) and recreate |
| Hook never starts | `CRON_NOTIFY_SECRET` missing or empty in container env |
| Watchtower in Docker, bot in Docker | Use `generic+http://host.docker.internal:18765/watchtower?secret=...` (with published host port) |
| Test without publishing port | `CRON_NOTIFY_MODE=docker ./scripts/notify_watchtower.sh "test"` |

Health check (inside container): `docker exec nas-telegram-bot curl -fsS http://127.0.0.1:18765/health`

---

## 6b. Watchtower (container image updates)

Watchtower can notify the bot when a new image is available (e.g. *New update available for Jellyfin*).

### Option A — Shoutrrr / generic HTTP (recommended)

In your Watchtower `docker-compose.yml`:

```yaml
services:
  watchtower:
    image: containrrr/watchtower
    environment:
      WATCHTOWER_NOTIFICATIONS: shoutrrr
      # Same secret as CRON_NOTIFY_SECRET in the bot .env
      WATCHTOWER_NOTIFICATION_URL: >-
        generic+http://127.0.0.1:18765/watchtower?secret=YOUR_CRON_NOTIFY_SECRET
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

Shoutrrr sends JSON with `title` and `message`; the bot formats it as a **Watchtower** Telegram alert.

- **Bot + Watchtower on host:** `127.0.0.1:18765` (bot must run on host, not only in Docker).
- **Bot in Docker (this repo’s compose):** publish `127.0.0.1:18765` on the host (default in `docker-compose.yml`), then use `127.0.0.1` from the host or `host.docker.internal` from another container.
- **Watchtower in Docker:** `host.docker.internal:18765` + `extra_hosts: host.docker.internal:host-gateway` (see compose below).
- **Watchtower in Docker, no published port:** `docker exec nas-telegram-bot curl ...` or set `CRON_NOTIFY_MODE=docker` for the test script.

**Watchtower `docker-compose.yml` (works with bot compose port publish):**

```yaml
services:
  watchtower:
    image: containrrr/watchtower:latest
    container_name: watchtower
    restart: unless-stopped
    environment:
      WATCHTOWER_NOTIFICATIONS: shoutrrr
      WATCHTOWER_NOTIFICATION_URL: >-
        generic+http://host.docker.internal:18765/watchtower?secret=YOUR_CRON_NOTIFY_SECRET
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

### Option B — POST from a script

```bash
# Loads CRON_NOTIFY_SECRET from repo .env if present
./scripts/notify_watchtower.sh "New update available for jellyfin"
```

### Option C — JSON to `/notify`

```bash
curl -fsS -X POST http://127.0.0.1:18765/notify \
  -H "Content-Type: application/json" \
  -d '{"secret":"YOUR_SECRET","source":"watchtower","message":"New update available for jellyfin"}'
```

**Note:** The bot’s built-in `UPTIME_DOCKER_IMAGE_ALERTS` also detects image ID changes on its own; Watchtower tells you *before* you pull/recreate.

---

## 7. Docker image update alerts

When a container’s image ID changes (pull/recreate), you get a Telegram message.

- Enabled: `UPTIME_DOCKER_IMAGE_ALERTS=true` (default)  
- Manual scan: `/monitor_images`  
- Automatic: every ~1h by default (`UPTIME_DOCKER_IMAGE_SCAN_TICKS=120` at 30s tick)  

Requires Docker socket access.

---

## 8. NAS reboot detection

Compares `psutil.boot_time()` each uptime tick. On change → **NAS reboot detected** alert.

- `UPTIME_REBOOT_ALERT_ENABLED=true` (default)  

Works in container with `pid: host` or on bare metal.

---

## 9. Optional web dashboard (Tailscale)

**Telegram (recommended):**

```
/monitor_dashboard on     — start + send link
/monitor_dashboard link   — resend link
/monitor_dashboard off    — disable
/monitor_dashboard status — show state
```

The bot reminds you to **connect to Tailscale** before opening the link.

```env
UPTIME_DASHBOARD_PUBLIC_HOST=100.75.87.91
UPTIME_DASHBOARD_PORT=18766
UPTIME_DASHBOARD_LISTEN=0.0.0.0
UPTIME_DASHBOARD_SECRET=your-long-random-secret
```

Link format: `http://100.75.87.91:18766/?secret=...` (secret in URL for browser + WebSocket).

After enabling, publish port **18766** in `docker-compose` and `docker compose up -d --force-recreate`.

Optional auto-start on boot: `UPTIME_DASHBOARD_ENABLED=true`.

Install deps: `pip install fastapi uvicorn` (included in `requirements.txt`).

---

## 10. Telegram commands (monitoring)

| Command | Purpose |
|---------|---------|
| `/monitors` | List all monitors |
| `/monitor_add` | Add monitor |
| `/monitor_stats` | MTBF, MTTR, latency sparkline |
| `/monitor_report` | Weekly summary |
| `/monitor_discover` | Sync Docker monitors |
| `/monitor_dep` | Dependency parent→child |
| `/monitor_silence` | Mute alerts N minutes |
| `/alerts` / `/alert_ack` | Alert inbox |
| `/monitor_groups` | List groups |
| `/monitor_images` | Force image scan |

---

## 11. Troubleshooting

| Symptom | Fix |
|---------|-----|
| No alerts at all | Check `ALLOWED_USER_IDS`, bot started, `UPTIME_MONITORING_ENABLED=true` |
| Ping monitors always fail | Install `ping`; container may need `NET_RAW` |
| Tailscale monitor fails | **Docker TS:** `UPTIME_TAILSCALE_PROBE=docker` and `UPTIME_TAILSCALE_CONTAINER=your_container_name` (restart bot). Or `/monitor_pause tailscale-mesh`. Host install: `tailscale` CLI in PATH |
| systemd/process monitors fail | Set `HOST_EXEC_MODE=nsenter` or `ssh` |
| `/proc` process monitor empty | Use `pid: host` in compose |
| Docker monitors empty | Mount `docker.sock` |
| Too many alerts | `/monitor_silence`, `/monitor_pause`, `MONITOR_DOCKER_IGNORE` |
| AI assist button missing | `OPENAI_API_KEY` + `UPTIME_AI_BUTTON=true` (default) |
| Auto AI on every DOWN | Set `UPTIME_AI_ON_INCIDENT=true` (default is **off**; use button instead) |

---

## 12. Start the bot

```bash
cd /workspace   # or your install path
source venv/bin/activate
pip install -r requirements.txt
python bot.py
```

Verify logs contain:

```text
Uptime monitoring engine started
Starting monitoring: health ...
```

Then in Telegram: `/monitors` — you should see built-in + discovered monitors within one tick (~30s).
