# NAS Bot — Monitoring & Alerting Setup Guide

This guide covers everything to configure **before** (and when) you run the bot so background monitoring and Telegram alerts work on your NAS.

## Quick checklist

| Requirement | Why |
|-------------|-----|
| `TELEGRAM_TOKEN` + `ALLOWED_USER_IDS` | Alerts are sent as Telegram DMs |
| `OPENAI_API_KEY` | Optional; AI incident summaries (`UPTIME_AI_ON_INCIDENT`) |
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

# AI on new incidents (uses API credits)
UPTIME_AI_ON_INCIDENT=true
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

## 9. Optional web dashboard

```env
UPTIME_DASHBOARD_ENABLED=true
UPTIME_DASHBOARD_BIND=127.0.0.1
UPTIME_DASHBOARD_PORT=18766
UPTIME_DASHBOARD_SECRET=your-secret
```

Access (SSH tunnel):

```bash
ssh -L 18766:127.0.0.1:18766 user@nas
# Browser: http://127.0.0.1:18766/  Header: X-Dashboard-Secret: your-secret
```

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
| AI summary missing | `OPENAI_API_KEY` + `UPTIME_AI_ON_INCIDENT=true` |

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
