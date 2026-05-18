# Docker Management

Complete guide to managing Docker containers via the NAS Telegram AI Assistant.

---

## Overview

Control and monitor Docker containers directly from Telegram:
- List all containers with status
- Start, stop, restart containers
- View container logs
- Monitor resource usage
- Container health detection

---

## Commands

### `/docker` or `/containers`

List all Docker containers with status and resource usage.

**Example**:
```
🐳 Docker Containers

nginx ✅ Running
├ CPU: 2%
├ RAM: 45 MB
└ Up: 5 days

postgres ✅ Running
├ CPU: 5%
├ RAM: 230 MB
└ Up: 5 days

redis ⏸ Stopped
└ Exited 2 hours ago
```

---

### `/restart <container>`

Restart a container.

```
/restart nginx
⚙️ Restarting nginx...
✅ Container nginx restarted successfully!
```

---

### `/stop <container>`

Stop a running container.

```
/stop nginx
⏸ Stopping nginx...
✅ Container nginx stopped successfully!
```

---

### `/start <container>`

Start a stopped container.

```
/start redis
▶️ Starting redis...
✅ Container redis started successfully!
```

---

### `/logs <container> [lines]`

View container logs.

```
/logs nginx 20
📋 Last 20 lines from nginx:

2026-05-18 09:00:01 GET /api/status 200
2026-05-18 09:00:05 GET /health 200
...
```

---

## Setup

### Docker Socket Access

For Docker commands to work, the bot needs access to Docker socket.

**Bare Metal**:
```bash
# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

**Docker**:

In `docker-compose.yml`:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

---

## Container Status Indicators

- ✅ **Running**: Container is active
- ⏸ **Stopped**: Container stopped normally
- ⚠️ **Exited**: Container crashed
- 🔄 **Restarting**: Container restarting
- 🏥 **Unhealthy**: Health check failing

---

## Resource Monitoring

Each container shows:
- **CPU %**: Percentage of CPU used
- **RAM**: Memory usage
- **Uptime**: How long running

**Alerts**:
- High CPU (> 80%) flagged
- High memory (> 1GB) flagged
- Unhealthy containers highlighted

---

## Automated Alerts

### Container Crash

Bot automatically alerts when container stops unexpectedly:

```
⚠️ Container Stopped

postgres container exited

Status: Exit code 1
Last log: Error: database corruption

Action: Check /logs postgres for details
```

### Unhealthy Container

If container health check fails:

```
🏥 Container Unhealthy

nginx health check failing

Duration: 5 minutes
Action: Investigate with /logs nginx
```

---

## Best Practices

### Regular Monitoring

- Daily `/docker` check
- Review container logs weekly
- Monitor resource usage trends

### Container Management

**Before restart**:
1. Check if necessary: `/logs <container>`
2. Verify impact on services
3. Restart during low-traffic times

**After restart**:
1. Verify started: `/docker`
2. Check logs: `/logs <container> 50`
3. Monitor for errors

### Security

- Limit container privileges
- Keep images updated
- Review logs for suspicious activity
- Use healthchecks

---

## Troubleshooting

### Docker Commands Fail

**Error**: `Failed to connect to Docker`

**Solutions**:
1. Verify Docker running: `docker ps`
2. Check socket mounted (Docker deployment)
3. Verify user in docker group (bare metal)
4. Check bot logs

### Container Won't Start

**Solutions**:
1. Check logs: `/logs <container>`
2. Verify required volumes exist
3. Check port conflicts
4. Verify image exists
5. Check resource limits

### High Resource Usage

**Solutions**:
1. Identify heavy containers: `/docker`
2. Check logs for issues
3. Adjust resource limits
4. Optimize application
5. Scale horizontally if needed

---

**Related**:
- [[Commands Reference|Commands-Reference]] - All Docker commands
- [[Docker Deployment|Docker-Deployment]] - Bot Docker setup
- [[Troubleshooting]] - Common issues
