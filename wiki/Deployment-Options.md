# Deployment Options

Production deployment strategies for the NAS Telegram AI Assistant.

---

## Deployment Methods

### 1. Docker Compose (Recommended)

**Best for**: Most users, easy management

**Pros**:
- Easy to deploy and update
- Isolated environment
- Resource limits
- Auto-restart
- Cross-platform

**Setup**:
```bash
cd BOT
cp .env.example .env
# Edit .env
docker-compose up -d
```

**Management**:
```bash
docker-compose logs -f      # View logs
docker-compose restart      # Restart
docker-compose down         # Stop
docker-compose pull && docker-compose up -d  # Update
```

---

### 2. Systemd Service (Bare Metal)

**Best for**: Direct hardware control, custom setups

**Pros**:
- No Docker overhead
- Direct system access
- Lower resource usage
- Traditional Linux service

**Setup**:

1. Install bot (see [[Installation]])

2. Create service file:
   ```bash
   sudo nano /etc/systemd/system/nas-telegram-bot.service
   ```

3. Add configuration:
   ```ini
   [Unit]
   Description=NAS Telegram AI Assistant
   After=network.target docker.service

   [Service]
   Type=simple
   User=yourusername
   WorkingDirectory=/opt/nas-telegram-bot/BOT
   Environment="PATH=/opt/nas-telegram-bot/BOT/venv/bin"
   ExecStart=/opt/nas-telegram-bot/BOT/venv/bin/python bot.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

4. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable nas-telegram-bot
   sudo systemctl start nas-telegram-bot
   ```

**Management**:
```bash
sudo systemctl status nas-telegram-bot
sudo systemctl restart nas-telegram-bot
sudo journalctl -u nas-telegram-bot -f
```

---

### 3. Screen/Tmux

**Best for**: Quick testing, temporary deployments

**Pros**:
- Simple
- No systemd needed
- Easy to attach/detach

**Setup**:
```bash
screen -S nas-bot
cd /opt/nas-telegram-bot/BOT
source venv/bin/activate
python bot.py

# Detach: Ctrl+A, D
# Reattach: screen -r nas-bot
```

---

### 4. Synology NAS

**Via Docker**:
1. Open Docker package
2. Registry → Search "python"
3. Create custom image from Dockerfile
4. Or use docker-compose.yml via SSH

**Paths**:
```env
DOCUMENT_PATH=/volume1/documents
ALLOWED_PATHS=/volume1/documents,/volume1/docker
DATABASE_PATH=/volume1/docker/nas-bot/data/bot.db
```

---

### 5. QNAP NAS

**Via Container Station**:
1. Open Container Station
2. Create → From Image
3. Use docker-compose.yml
4. Configure volumes

**Paths**:
```env
DOCUMENT_PATH=/share/documents
ALLOWED_PATHS=/share/documents,/share/data
```

---

### 6. Cloud VPS

**Platforms**: DigitalOcean, Linode, Vultr, AWS EC2

**Recommended Specs**:
- 2 vCPU
- 4GB RAM
- 20GB disk
- Ubuntu 22.04 LTS

**Setup**: Same as Docker Compose or Systemd

---

## High Availability Setup

### Docker Swarm (Advanced)

For redundancy across multiple servers:

```yaml
version: '3.8'
services:
  nas-bot:
    image: nas-telegram-bot:latest
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
      placement:
        constraints:
          - node.role == manager
```

### Health Checks

Built-in health check in Dockerfile:
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s \
  CMD python -c "import os; exit(0 if os.path.exists('data/bot.db') else 1)"
```

---

## Auto-Start on Boot

### Docker Compose

```yaml
restart: unless-stopped  # Already in docker-compose.yml
```

### Systemd

```bash
sudo systemctl enable nas-telegram-bot
```

### Synology

1. Control Panel → Task Scheduler
2. Create → Triggered Task → User-defined script
3. Boot-up trigger
4. Script: `docker start nas-telegram-bot`

---

## Backup Strategies

### What to Backup

- `data/` directory (database + ChromaDB)
- `.env` file (configuration)
- `logs/` directory (optional)
- `documents/` (if storing locally)

### Automated Backup Script

```bash
#!/bin/bash
# backup-bot.sh

DATE=$(date +%Y%m%d)
BACKUP_DIR="/backups/nas-bot"

mkdir -p $BACKUP_DIR

# Backup data
tar -czf $BACKUP_DIR/data-$DATE.tar.gz -C /path/to/BOT data/

# Backup .env
cp /path/to/BOT/.env $BACKUP_DIR/.env-$DATE

# Keep last 30 days
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
```

### Cron Job

```bash
# Daily backup at 3 AM
0 3 * * * /path/to/backup-bot.sh
```

---

## Monitoring

### Check Status

**Docker**:
```bash
docker ps | grep nas-telegram-bot
docker stats nas-telegram-bot
```

**Systemd**:
```bash
systemctl status nas-telegram-bot
journalctl -u nas-telegram-bot --since today
```

### Resource Monitoring

```bash
# CPU and memory
docker stats --no-stream nas-telegram-bot

# Disk usage
du -sh data/ logs/
```

### Log Monitoring

```bash
# Watch logs
tail -f logs/bot.log

# Search for errors
grep ERROR logs/bot.log | tail -20

# Count commands today
grep "$(date +%Y-%m-%d)" logs/bot.log | grep "command:" | wc -l
```

---

## Update Procedures

### Docker Compose

```bash
cd /path/to/BOT

# Pull latest code
git pull

# Rebuild image
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Verify
docker-compose logs -f
```

### Systemd

```bash
# Stop service
sudo systemctl stop nas-telegram-bot

# Update code
cd /opt/nas-telegram-bot
git pull

# Update dependencies
source BOT/venv/bin/activate
pip install --upgrade -r BOT/requirements.txt

# Restart
sudo systemctl start nas-telegram-bot
```

---

## Security in Production

1. **Firewall**: Only needed ports (none for bot)
2. **SSH Keys**: Disable password auth
3. **Updates**: Regular system updates
4. **Monitoring**: Alert on failures
5. **Backups**: Automated and tested
6. **Secrets**: `.env` permissions 600
7. **Users**: Limit `ALLOWED_USER_IDS`

---

## Troubleshooting Deployments

### Bot Won't Start After Reboot

**Check**: Auto-start configuration

**Docker**:
```yaml
restart: unless-stopped
```

**Systemd**:
```bash
sudo systemctl enable nas-telegram-bot
```

### High Resource Usage

**Solutions**:
- Set Docker resource limits
- Reduce indexed documents
- Clear old logs
- Optimize queries

### Network Issues

**Check**:
- Internet connectivity
- DNS resolution
- Firewall rules
- Telegram API access

---

## Production Checklist

- [ ] Bot running and responding
- [ ] Auto-start configured
- [ ] Backups automated
- [ ] Logs rotating
- [ ] Monitoring in place
- [ ] `.env` secured
- [ ] Resource limits set
- [ ] Documentation updated
- [ ] Team trained
- [ ] Incident response plan

---

**Related**:
- [[Docker Deployment|Docker-Deployment]] - Docker details
- [[Installation]] - Bare metal setup
- [[Security]] - Security best practices
