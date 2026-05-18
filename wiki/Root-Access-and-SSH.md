# Root Access and SSH

Complete guide to elevated access features in the NAS Telegram AI Assistant.

---

## Overview

The bot provides temporary elevated access for advanced operations:
- **Root Access**: Full file system access for 30 minutes
- **SSH Commands**: Execute shell commands via `/ssh`
- **Security**: Password-protected with comprehensive logging
- **Auto-Expire**: Sessions automatically end after timeout

---

## What is Root Access?

### Standard Access

Without root access, you are limited to:
- Paths defined in `ALLOWED_PATHS`
- Read-only operations for most paths
- No shell command execution

### Root Access

With root access, you gain:
- Full file system access (`/`)
- Read and write permissions
- Ability to execute shell commands via `/ssh`
- Upload files anywhere with `/uploadfile`

### Security Model

- **Password Protected**: Requires `ROOT_PASSWORD` from `.env`
- **Time-Limited**: Automatically expires after 30 minutes
- **Fully Logged**: All actions logged for security audit
- **User-Specific**: Each user has independent sessions

---

## Root Access Commands

### `/rootlogin <password>`

Activate temporary root access.

**Usage**:
```
/rootlogin YourSecurePassword123!
```

**Response**:
```
🔓 Root Access Granted

You now have full file system access for 30 minutes.

⚠️ All actions are logged.
Use /rootstatus to check remaining time.
Use /rootlogout to end session early.
```

**What Changes**:
- File access: `ALLOWED_PATHS` → All paths (`/`)
- Commands: `/ssh` becomes available
- Uploads: `/uploadfile` can write anywhere

**Failed Attempt**:
```
❌ Authentication Failed

Invalid password. This incident has been logged.
```

---

### `/rootstatus`

Check root session status and remaining time.

**Usage**:
```
/rootstatus
```

**With Active Session**:
```
🔓 Root Session Active

Started: 09:00:00
Expires: 09:30:00
Time Remaining: 18m 35s

⚠️ All actions are being logged.
```

**Without Active Session**:
```
🔒 No Active Root Session

You are using standard file permissions.
Use /rootlogin <password> to activate root access.
```

---

### `/rootlogout`

End root session early (before 30-minute timeout).

**Usage**:
```
/rootlogout
```

**Response**:
```
🔒 Root Session Ended

File access restored to normal permissions.
```

**Best Practice**: Always logout when done with root operations.

---

## SSH Command Execution

### `/ssh <command>`

Execute shell commands on your NAS.

**Requirements**: Active root session

**Usage**:
```
/ssh <command>
```

**Examples**:

#### List Files
```
You: /ssh ls -la
Bot: ✅ Exit Code: 0

Output:
total 42
drwxr-xr-x  5 user user  4096 May 18 09:00 .
drwxr-xr-x 12 user user  4096 May 18 08:30 ..
-rw-r--r--  1 user user  1234 May 18 09:00 file.txt
...
```

#### Check Disk Space
```
You: /ssh df -h
Bot: ✅ Exit Code: 0

Output:
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       1.0T  450G  550G  45% /
/dev/sdb1       4.0T  2.8T  1.2T  70% /volume1
```

#### Docker Commands
```
You: /ssh docker ps
Bot: [Shows running containers]

You: /ssh docker logs nginx --tail 50
Bot: [Shows nginx logs]
```

#### System Commands
```
You: /ssh systemctl status nginx
You: /ssh top -bn1 | head -20
You: /ssh free -h
You: /ssh ps aux | grep python
```

#### File Operations
```
You: /ssh mkdir /app/documents/NewFolder
Bot: ✅ Directory created

You: /ssh cp file1.txt file2.txt
You: /ssh rm old_file.txt
```

---

### SSH Command Features

#### Default Working Directory

Commands without absolute paths run in `/app/documents`:

```
# These are equivalent:
/ssh ls
/ssh cd /app/documents && ls
```

**Why**: Shows your documents by default, not bot code.

#### Command Timeout

- Commands have 60-second timeout
- Prevents hanging operations
- Long operations show timeout error

**Example**:
```
You: /ssh sleep 120
Bot: ❌ Command Timeout

Command: sleep 120
The command took longer than 60 seconds to execute.
```

#### Exit Codes

Bot shows exit codes to indicate success/failure:

- **Exit Code 0**: Success ✅
- **Exit Code > 0**: Error ❌

**Example**:
```
You: /ssh cat nonexistent.txt
Bot: ❌ Exit Code: 1

Errors:
cat: nonexistent.txt: No such file or directory
```

#### Output Formatting

- **stdout**: Shown as "Output"
- **stderr**: Shown as "Errors"
- **Truncation**: Long output truncated to fit Telegram limit

---

## Use Cases

### 1. Advanced File Management

```
/rootlogin <password>

# Create directory structure
/ssh mkdir -p /data/backups/2026/05

# Move files
/ssh mv /documents/old/* /archive/

# Check file sizes
/ssh du -sh /data/*

/rootlogout
```

### 2. System Maintenance

```
/rootlogin <password>

# Check system logs
/ssh tail -100 /var/log/syslog

# Clean up
/ssh apt-get autoclean
/ssh docker system prune -f

# Update packages
/ssh apt-get update

/rootlogout
```

### 3. Docker Management

```
/rootlogin <password>

# Inspect container
/ssh docker inspect nginx

# Execute command in container
/ssh docker exec postgres psql -U user -c "SELECT version();"

# Clean up
/ssh docker system df
/ssh docker volume prune -f

/rootlogout
```

### 4. Permissions Fix

```
/rootlogin <password>

# Fix file permissions
/ssh chmod -R 755 /data/public
/ssh chown -R user:user /documents

# Fix directory ownership
/ssh chown root:root /etc/config

/rootlogout
```

### 5. Quick Diagnostics

```
/rootlogin <password>

# Check process
/ssh ps aux | grep nginx

# Network diagnostics
/ssh netstat -tulpn | grep LISTEN

# Disk I/O
/ssh iostat -x 1 5

/rootlogout
```

---

## Security Considerations

### Password Security

**Strong Password Requirements**:
- Minimum 12 characters
- Mix of uppercase, lowercase, numbers, symbols
- Not used elsewhere
- Not based on dictionary words

**Example Good Passwords**:
- `MyNAS!Secure#2026`
- `T3l3gr4m!Root@Home`
- `SecureN45!Access#`

**Bad Passwords**:
- `password123`
- `admin`
- `nas2026`

### Audit Logging

Every root action is logged:

**Login Attempts**:
```log
2026-05-18 09:00:00 - WARNING - User 123456789 gained root access
2026-05-18 09:05:30 - WARNING - Failed root login attempt by user 987654321
```

**SSH Commands**:
```log
2026-05-18 09:01:15 - WARNING - User 123456789 executing SSH command: ls -la
2026-05-18 09:02:30 - WARNING - User 123456789 executing SSH command: docker ps
```

**Session End**:
```log
2026-05-18 09:15:00 - WARNING - User 123456789 ended root session
2026-05-18 09:30:00 - INFO - Root session expired for user 123456789
```

### Monitoring Root Access

**Review logs regularly**:
```bash
# Check bot logs
tail -f logs/bot.log | grep -i "root\|ssh"

# Count root logins today
grep "root access" logs/bot.log | grep "$(date +%Y-%m-%d)" | wc -l

# List all SSH commands
grep "executing SSH command" logs/bot.log
```

### Best Practices

1. **Use Only When Needed**
   - Don't stay logged in
   - Logout immediately after task

2. **Be Careful with Commands**
   - Double-check destructive operations
   - Use `--dry-run` flags when available
   - Backup before major changes

3. **Regular Password Rotation**
   - Change `ROOT_PASSWORD` quarterly
   - Update `.env` and restart bot

4. **Limit User Access**
   - Only trusted users in `ALLOWED_USER_IDS`
   - Remove users who no longer need access

5. **Monitor Activity**
   - Review logs weekly
   - Investigate suspicious commands
   - Set up alerts for sensitive operations

---

## Dangerous Commands Warning

Be extremely careful with these commands:

### Destructive Operations

```bash
# Can delete all files!
rm -rf /  # NEVER RUN THIS

# Can delete user data
rm -rf /home/*

# Can break system
chmod -R 777 /

# Can fill disk
dd if=/dev/zero of=/bigfile
```

### System Changes

```bash
# Can break boot
rm /boot/*

# Can corrupt packages
dpkg --force-all

# Can disconnect network
ifconfig eth0 down
```

### Always Include Confirmation

For destructive operations, check twice:

```
# Before deleting
/ssh ls -la /path/to/delete
# [Verify it's correct]

# Then delete
/ssh rm -rf /path/to/delete
```

---

## Troubleshooting

### Cannot Login

**Error**: "Authentication Failed"

**Solutions**:
1. Verify password in `.env`
2. Check for typos (case-sensitive)
3. Restart bot if password just changed
4. Review logs for details

### SSH Command Unavailable

**Error**: "Root Access Required"

**Solutions**:
1. Login first: `/rootlogin <password>`
2. Check session active: `/rootstatus`
3. Re-login if expired

### Command Fails

**Error**: Various command errors

**Solutions**:
1. Check command syntax
2. Verify permissions
3. Check if tool installed
4. Review error message
5. Test command in regular SSH first

### Session Expires Too Soon

**Issue**: 30 minutes not enough

**Solution**: 

Modify timeout in `utils/root_session.py`:
```python
SESSION_TIMEOUT = timedelta(minutes=60)  # Change to 60 minutes
```

Restart bot.

**Security Note**: Longer sessions = more risk

---

## Emergency Procedures

### Lost Root Access

If you can't login:

1. **SSH to server directly**
   ```bash
   ssh user@nas-ip
   ```

2. **Check .env file**
   ```bash
   cd /path/to/BOT
   cat .env | grep ROOT_PASSWORD
   ```

3. **Update password**
   ```bash
   nano .env  # Change ROOT_PASSWORD
   ```

4. **Restart bot**
   ```bash
   docker-compose restart
   # or
   systemctl restart nas-telegram-bot
   ```

### Accidental Command

If you ran a dangerous command:

1. **Stop immediately** (if still running)
2. **Assess damage**:
   ```
   /ssh ls -la /affected/path
   /disk
   ```
3. **Restore from backup**
4. **Review what happened** in logs

---

## Alternatives to Root Access

For specific tasks, consider safer alternatives:

### File Operations

Instead of root + `/ssh`:
```
Use: /ls, /download, /find
```

### Container Management

Instead of `/ssh docker`:
```
Use: /docker, /restart, /logs
```

### System Status

Instead of `/ssh ps`, `/ssh df`:
```
Use: /status, /cpu, /disk
```

**Rule**: Use root only for operations that truly require it.

---

**Related**:
- [[Commands Reference|Commands-Reference]] - All root commands
- [[File Management|File-Management]] - File operations
- [[Security]] - Security model
- [[Configuration Guide|Configuration-Guide]] - ROOT_PASSWORD setup
