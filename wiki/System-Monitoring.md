# System Monitoring

Complete guide to system monitoring features in the NAS Telegram AI Assistant.

---

## Overview

The bot provides comprehensive real-time monitoring of your NAS system, including:
- CPU usage and load
- Memory (RAM) utilization
- Disk space and usage
- Temperature sensors
- Network statistics
- System uptime
- Health scoring
- SMART drive health

---

## Monitoring Commands

### `/status` - Quick Overview

Get a comprehensive snapshot of your system:

```
🖥 System Status

💻 CPU: 45% (Load: 2.1, 1.8, 1.5)
🧠 RAM: 3.2GB / 8GB (40%)
💾 Disk: 450GB / 1TB (45%)
🌡 Temp: 52°C
🌐 Network: ↓15MB/s ↑2MB/s
⏰ Uptime: 5 days, 3 hours
```

**Best for**: Quick health check, daily monitoring

---

### `/cpu` - CPU Details

View detailed CPU metrics:

**Displays**:
- Overall CPU usage percentage
- Per-core usage
- Load averages (1, 5, 15 min)
- CPU frequency

**Understanding Load Average**:
- **< 1.0**: System healthy
- **1.0-2.0**: Moderate load
- **> 2.0**: High load (may slow down)

**Example**:
```
💻 CPU Usage

Overall: 45.2%
Core 1: 60% | Core 2: 38%
Core 3: 42% | Core 4: 40%

Load Average:
1 min: 2.10
5 min: 1.85
15 min: 1.50
```

---

### `/ram` - Memory Usage

Monitor RAM utilization:

**Displays**:
- Total RAM
- Used RAM
- Available RAM
- Cached memory
- Swap usage

**When to worry**:
- **> 80%**: Consider adding RAM or reducing services
- **Swap active**: System may be slow
- **Continuous growth**: Possible memory leak

**Example**:
```
🧠 Memory Usage

Total: 8.0 GB
Used: 3.2 GB (40%)
Available: 4.8 GB
Cached: 2.1 GB

Swap: 2.0 GB
Swap Used: 0.5 GB (25%)
```

---

### `/disk` - Disk Space

Check disk usage across all filesystems:

**Displays**:
- All mounted filesystems
- Total, used, free space
- Usage percentage
- Mount points

**Alert Thresholds**:
- **> 80%**: Warning
- **> 90%**: Critical
- **> 95%**: Immediate action needed

**Example**:
```
💾 Disk Usage

/ (root)
Total: 1.0 TB
Used: 450 GB (45%)
Free: 550 GB

/volume1
Total: 4.0 TB
Used: 2.8 TB (70%)
Free: 1.2 TB ⚠️
```

---

### `/temps` - Temperature Sensors

Monitor system temperatures:

**Displays**:
- CPU temperature
- Disk temperatures
- GPU temperature (if available)
- Other sensors

**Safe Ranges**:
- **CPU**: < 80°C normal, > 90°C concerning
- **Disk**: < 50°C ideal, > 60°C high
- **GPU**: < 85°C normal

**Example**:
```
🌡 Temperature Sensors

CPU: 52°C ✅
Disk 1 (sda): 38°C ✅
Disk 2 (sdb): 40°C ✅
GPU: 45°C ✅
```

**Note**: Requires `lm-sensors` on bare metal, built-in on Docker

---

### `/network` - Network Stats

View network activity and configuration:

**Displays**:
- Upload/download speeds
- Total bytes transferred
- IP addresses
- Tailscale IPs (if configured)

**Example**:
```
🌐 Network Statistics

eth0:
↓ Download: 15.2 MB/s
↑ Upload: 2.3 MB/s
Sent: 458 GB
Received: 1.2 TB

IP: 192.168.1.100
Tailscale: 100.64.1.50
Gateway: 192.168.1.1
```

---

### `/uptime` - System Uptime

Check how long system has been running:

**Displays**:
- Days, hours, minutes since boot
- Boot timestamp

**Example**:
```
⏱ System Uptime

5 days, 3 hours, 42 minutes

Started: 2026-05-13 05:18:00
```

**Tip**: Long uptimes are good, but update systems regularly

---

### `/health` - Health Score

Get an overall system health assessment:

**Displays**:
- Health score (0-100)
- Health status
- Detected issues
- Recommendations

**Scoring**:
- **90-100**: Excellent ✅
- **70-89**: Good 🟢
- **50-69**: Fair 🟡
- **30-49**: Poor 🟠
- **0-29**: Critical 🔴

**Health Factors**:
- CPU usage
- Memory usage
- Disk space
- Disk health (SMART)
- Service status
- Temperature

**Example**:
```
🟢 System Health: Good (85/100)

Issues:
⚠️ Disk /volume1 at 78% capacity
⚠️ Service nginx not running
⚠️ High CPU load (2.5)

Recommendations:
• Clean up /volume1 disk space
• Restart nginx service
• Investigate CPU usage
```

---

### `/smart` - Drive Health

Check SMART data for all drives:

**Displays**:
- Drive status (PASSED/FAILED)
- Temperature
- Power-on hours
- Reallocated sectors
- Pending sectors
- Read/write errors

**SMART Status**:
- **PASSED**: Drive healthy ✅
- **FAILED**: Drive failing ⚠️
- **UNAVAILABLE**: SMART not supported or disabled

**Example**:
```
💿 Drive Health (SMART)

/dev/sda (WD Red 4TB)
Status: PASSED ✅
Temp: 38°C
Power On: 12,450 hours (1.4 years)
Reallocated Sectors: 0
Pending Sectors: 0
Read Errors: 0

/dev/sdb (Seagate 2TB)
Status: PASSED ✅
Temp: 40°C
Power On: 8,200 hours (0.9 years)
Reallocated Sectors: 0
```

**Critical Indicators**:
- **Reallocated sectors > 0**: Drive degrading
- **Pending sectors > 0**: Drive issues
- **Status FAILED**: Replace immediately!

---

### `/drives` - Drive List

List all detected drives:

**Displays**:
- Device names
- Capacity
- Model
- Serial numbers
- Type (HDD/SSD)

**Example**:
```
💿 System Drives

sda: WD Red 4TB (HDD)
    Model: WDC WD40EFRX
    Serial: WD-WCC7K1234567
    
sdb: Seagate 2TB (HDD)
    Model: ST2000DM008
    Serial: ZDH12345
    
nvme0n1: Samsung 970 EVO 1TB (SSD)
    Model: Samsung SSD 970 EVO 1TB
    Serial: S5H7NS0M123456
```

---

## Automated Alerts

The bot automatically monitors your system and sends alerts for:

### Low Disk Space

**Threshold**: > 80% full

**Alert**:
```
⚠️ Disk Space Alert

/volume1 is 85% full

Total: 4.0 TB
Used: 3.4 TB
Free: 600 GB

Action: Clean up files or expand storage
```

---

### High CPU Usage

**Threshold**: > 90% for 5+ minutes

**Alert**:
```
⚠️ High CPU Usage

CPU at 95% for 8 minutes

Top processes:
- ffmpeg: 45%
- python: 30%
- docker: 15%

Action: Check if this is expected or investigate
```

---

### High Memory Usage

**Threshold**: > 90%

**Alert**:
```
⚠️ High Memory Usage

RAM: 7.8 GB / 8 GB (98%)

Consider:
- Restarting memory-heavy services
- Adding more RAM
- Checking for memory leaks
```

---

### Temperature Warnings

**Threshold**: CPU > 85°C, Disk > 55°C

**Alert**:
```
🌡 Temperature Warning

CPU: 88°C (High)
Disk sda: 58°C (High)

Actions:
- Check cooling fans
- Clean dust from vents
- Improve airflow
```

---

### SMART Failures

**Trigger**: SMART status FAILED

**Alert**:
```
🚨 CRITICAL: Drive Failure Detected

/dev/sdb SMART Status: FAILED
Reallocated Sectors: 15
Pending Sectors: 3

IMMEDIATE ACTION REQUIRED:
1. Backup all data NOW
2. Replace drive ASAP
3. Check RAID status if applicable
```

---

### Container Crashes

**Trigger**: Container stops unexpectedly

**Alert**:
```
⚠️ Container Stopped

postgres container exited

Status: Exit code 1
Last log: Error: database corruption

Action: Check /logs postgres for details
```

---

## Health Scoring Algorithm

The health score is calculated based on multiple factors:

### CPU Score (20 points)

- **< 70%**: Full points (20)
- **70-85%**: Partial (15)
- **85-95%**: Low (10)
- **> 95%**: Critical (0)

### Memory Score (20 points)

- **< 80%**: Full points (20)
- **80-90%**: Partial (15)
- **> 90%**: Critical (0)

### Disk Score (25 points)

- **< 80%**: Full points (25)
- **80-90%**: Partial (15)
- **90-95%**: Low (10)
- **> 95%**: Critical (0)

### Temperature Score (15 points)

- **Normal**: Full points (15)
- **High**: Partial (8)
- **Critical**: (0)

### Services Score (10 points)

- **All running**: Full points (10)
- **Some down**: Proportional

### SMART Score (10 points)

- **All PASSED**: Full points (10)
- **Any FAILED**: (0)

**Total**: Sum of all categories (max 100)

---

## Best Practices

### Regular Monitoring

**Daily**:
- Quick `/status` check
- Review any alerts

**Weekly**:
- `/health` comprehensive check
- `/smart` drive health
- `/disk` usage trends

**Monthly**:
- Review all metrics
- Plan capacity upgrades
- Update systems

### Setting Up Monitoring Routine

Create a schedule:

```
Morning (9 AM):
/status - Quick check before work

Afternoon (3 PM):
/health - Mid-day health check

Evening (9 PM):
/status - End of day review
```

### Responding to Alerts

**Low Disk Space**:
1. Check what's using space: `/storage`
2. Clean up unneeded files
3. Archive old data
4. Plan expansion if needed

**High CPU**:
1. Check current usage: `/cpu`
2. Ask AI: "why is CPU high?"
3. Check Docker containers: `/docker`
4. Review running processes

**Temperature High**:
1. Check current temps: `/temps`
2. Verify fans working
3. Clean dust
4. Improve airflow
5. Consider better cooling

**SMART Failure**:
1. **Immediate**: Backup data
2. Order replacement drive
3. Monitor closely
4. Replace ASAP

---

## Interpreting Metrics

### CPU Load Average

**Single Core System**:
- **1.0**: 100% utilized
- **> 1.0**: Queue building up

**Multi-Core System** (4 cores):
- **4.0**: 100% utilized
- **< 4.0**: Capacity available
- **> 4.0**: Overloaded

**Rule of Thumb**: Load should be < number of cores

### Memory Usage

**Normal**: 40-70% used (includes cache)

**Cache Memory**: Not a problem!
- Linux caches frequently used files
- Released when applications need it
- High cache = better performance

**Swap Usage**:
- **Occasional**: Normal
- **Constant**: Add more RAM
- **Heavy**: Performance impacted

### Disk I/O

**Indicators of disk stress**:
- High wait times in `/cpu`
- Slow command responses
- Container performance issues

**Solutions**:
- Move to SSD
- Reduce concurrent I/O
- Upgrade disks
- Add cache

---

## Network Monitoring

### Understanding Speeds

**Typical NAS Usage**:
- **Idle**: < 1 MB/s
- **File transfer**: 50-110 MB/s (gigabit)
- **Streaming**: 5-25 MB/s
- **Backup**: Varies, sustained high

**Unusual Activity**:
- **Unexpected high upload**: Check for compromised services
- **Constant high traffic**: Possible crypto mining
- **No traffic when expected**: Network issues

### Tailscale Integration

If Tailscale configured, bot shows:
- Tailscale IP address
- Remote access status
- Allows monitoring from anywhere

---

## Troubleshooting

### Metrics Not Available

**Issue**: Some metrics show "unavailable"

**Causes**:
- Running in Docker without proper mounts
- Permissions issues
- Required tools not installed

**Solutions**:
- Check Docker mounts in `docker-compose.yml`
- Install `lm-sensors`, `smartmontools`
- Review bot logs

### Inaccurate Readings

**Issue**: Metrics seem wrong

**Solutions**:
1. Restart bot
2. Check system time is correct
3. Verify sensor calibration
4. Compare with other monitoring tools

### Alerts Not Working

**Issue**: Not receiving alerts

**Solutions**:
1. Check alert thresholds in config
2. Verify bot is running
3. Check Telegram notifications enabled
4. Review bot logs for errors

---

**Related Pages**:
- [[Commands Reference|Commands-Reference]] - All monitoring commands
- [[Docker Management|Docker-Management]] - Container monitoring
- [[Troubleshooting]] - Common issues
