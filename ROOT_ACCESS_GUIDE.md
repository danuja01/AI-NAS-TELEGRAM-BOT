# Root Access & SSH Command Guide

## Overview

The NAS Telegram Bot now supports temporary root access with the ability to execute shell commands directly from Telegram.

## Features

### 1. Root Access
- **Duration**: 30 minutes per session
- **Access**: All paths in the container (not just `/app/documents` and `/app/data`)
- **Security**: Password protected, all actions logged
- **Auto-expire**: Sessions automatically expire after 30 minutes

### 2. SSH Command Execution
- **Requirement**: Active root session
- **Timeout**: 60 seconds per command
- **Logging**: All commands are logged for security audit
- **Safety**: Commands run in the Docker container environment

## Usage

### Step 1: Login as Root

```
/rootlogin <password>
```

Example:
```
/rootlogin DH.jayy@2001#
```

**Response:**
```
🔓 Root Access Granted

You now have full file system access for 30 minutes.

⚠️ All actions are logged.
Use /rootstatus to check remaining time.
Use /rootlogout to end session early.
```

### Step 2: Execute Commands

```
/ssh <command>
```

**Examples:**

```bash
# List all directories
/ssh ls -la /app

# Check disk usage
/ssh df -h

# View system info
/ssh uname -a

# Create a directory
/ssh mkdir /app/test

# View running processes
/ssh ps aux

# Check Docker containers (if Docker socket mounted)
/ssh docker ps

# Network information
/ssh ip addr

# Read a file
/ssh cat /app/data/bot.db

# Find files
/ssh find /app -name "*.log"
```

### Step 3: Check Session Status

```
/rootstatus
```

**Response:**
```
🔓 Root Session Active

Started: 12:45:30
Expires: 13:15:30
Time Remaining: 25m 12s

⚠️ All actions are being logged.
```

### Step 4: Logout (Optional)

```
/rootlogout
```

**Response:**
```
🔒 Root Session Ended

File access restored to normal permissions.
```

## Command Output Format

The `/ssh` command returns:
- **Exit Code**: Success (0) or error code
- **Output**: Standard output from the command
- **Errors**: Standard error output (if any)
- **Truncation**: Long outputs are automatically truncated for Telegram's message limits

**Example Response:**
```
Command: `ls -la /app`

✅ Exit Code: 0

Output:
total 48
drwxr-xr-x 1 root root 4096 May 18 00:45 .
drwxr-xr-x 1 root root 4096 May 18 00:20 ..
drwxr-xr-x 2 root root 4096 May 18 00:45 data
drwxr-xr-x 2 root root 4096 May 18 00:45 logs
drwxr-xr-x 2 root root 4096 May 18 00:45 documents
```

## Security Features

1. **Password Protection**: Root access requires correct password
2. **Session Timeout**: Auto-expires after 30 minutes
3. **Comprehensive Logging**: All root actions are logged with WARNING level
4. **User Tracking**: User ID is recorded for all root operations
5. **Command Timeout**: Commands timeout after 60 seconds to prevent hanging
6. **Sandboxed**: Commands run within Docker container (not host system)

## Important Notes

### Path Access
- **Without root**: Limited to `/app/documents` and `/app/data`
- **With root**: Access to all paths in the Docker container (`/`)

### Command Limitations
- Maximum execution time: 60 seconds
- Output truncated if exceeds ~3500 characters
- Cannot access host system (runs in Docker container)
- Interactive commands (requiring input) won't work

### Best Practices
1. Always logout when done (`/rootlogout`)
2. Use `/rootstatus` to monitor session time
3. Be cautious with destructive commands (`rm`, `mv`, etc.)
4. Test commands with non-destructive flags first
5. Remember: All actions are logged and traceable

## Troubleshooting

### "Root Access Required" Error
**Problem**: Trying to use `/ssh` without active root session

**Solution**: Run `/rootlogin <password>` first

### "Authentication Failed" Error
**Problem**: Incorrect password provided

**Solution**: Double-check your password in `.env` file (`ROOT_PASSWORD`)

### "Command Timeout" Error
**Problem**: Command took longer than 60 seconds

**Solution**: Try optimizing the command or break it into smaller operations

### "No Active Root Session"
**Problem**: Session expired (30 minutes passed)

**Solution**: Login again with `/rootlogin <password>`

## Example Workflow

```
# 1. Login
/rootlogin DH.jayy@2001#

# 2. Check current directory
/ssh pwd

# 3. List files in restricted area
/ssh ls -la /app/DANUJA

# 4. Read a file
/ssh cat /app/DANUJA/config.txt

# 5. Create a backup
/ssh cp -r /app/data /app/backups

# 6. Check status
/rootstatus

# 7. Logout when done
/rootlogout
```

## Docker Container Context

Remember: Commands run **inside** the Docker container:
- `/app/data` → Container's data directory (mounted from `./data`)
- `/app/logs` → Container's logs directory (mounted from `./logs`)
- `/app/documents` → Container's documents directory (mounted from your `DOCUMENT_PATH`)

To access paths outside mounted volumes, you need to either:
1. Add more volume mounts in `docker-compose.yml`
2. Use root access to work within container filesystem only

## Security Logs

All root activities are logged:
```
2026-05-18 00:45:30 - WARNING - Root session created for user 8346314011
2026-05-18 00:46:15 - WARNING - User 8346314011 executing SSH command: ls -la /app
2026-05-18 01:15:30 - WARNING - Root session ended for user 8346314011 (duration: 0:30:00)
```

Check logs with:
```bash
docker logs nas-telegram-bot | grep WARNING
```
