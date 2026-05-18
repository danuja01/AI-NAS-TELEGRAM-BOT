# Commands Reference

Complete catalog of all available commands for the NAS Telegram AI Assistant.

---

## Table of Contents

1. [Command Categories](#command-categories)
2. [General Commands](#general-commands)
3. [System Monitoring](#system-monitoring)
4. [Docker Management](#docker-management)
5. [File System](#file-system)
6. [Service Management](#service-management)
7. [AI Assistant](#ai-assistant)
8. [Root Access](#root-access)
9. [Command Tips](#command-tips)

---

## Command Categories

| Category | Commands | Purpose |
|----------|----------|---------|
| **General** | `/start`, `/help` | Getting started and help |
| **Monitoring** | `/status`, `/cpu`, `/ram`, `/disk`, `/temps`, `/network`, `/uptime`, `/health`, `/smart`, `/drives` | System monitoring and health |
| **Docker** | `/docker`, `/containers`, `/restart`, `/stop`, `/start`, `/logs` | Container management |
| **Files** | `/files`, `/ls`, `/download`, `/uploadfile`, `/find`, `/tree`, `/storage` | File operations |
| **Services** | `/services`, `/restart_service`, `/reboot`, `/shutdown` | Service control |
| **AI** | `/ask`, `/chat`, `/summarize`, `/explain`, `/analyze`, `/think`, `/websearch`, `/index`, `/clear` | AI and RAG features |
| **Root** | `/rootlogin`, `/rootstatus`, `/rootlogout`, `/ssh` | Elevated access |

---

## General Commands

### `/start`

**Purpose**: Welcome message and bot introduction

**Usage**:
```
/start
```

**Response**:
- Welcome message
- Feature overview
- Link to help

**Example**:
```
You: /start
Bot: 👋 Welcome to NAS AI Assistant!
     I can help you with system monitoring, Docker...
```

---

### `/help`

**Purpose**: Show all available commands

**Usage**:
```
/help
```

**Response**:
- Complete command list
- Organized by category
- Usage tips

**Example**:
```
You: /help
Bot: 📚 Available Commands
     
     📊 Monitoring
     /status - System overview
     /cpu - CPU usage
     ...
```

---

## System Monitoring

### `/status`

**Purpose**: Comprehensive system overview

**Usage**:
```
/status
```

**Shows**:
- CPU usage and load
- Memory usage
- Disk usage
- Network statistics
- System uptime
- Temperature sensors (if available)

**Example Output**:
```
🖥 System Status

💻 CPU: 45% (Load: 2.1, 1.8, 1.5)
🧠 RAM: 3.2GB / 8GB (40%)
💾 Disk: 450GB / 1TB (45%)
🌡 Temp: 52°C
🌐 Network: ↓15MB/s ↑2MB/s
⏰ Uptime: 5 days, 3 hours
```

**Tips**:
- Use for quick health check
- Run regularly to monitor trends
- Follow up with specific commands for details

---

### `/cpu`

**Purpose**: Detailed CPU information

**Usage**:
```
/cpu
```

**Shows**:
- Current CPU usage percentage
- Per-core usage
- Load averages (1, 5, 15 minutes)
- CPU frequency

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

Frequency: 2.4 GHz
```

**Follow-up**: Ask AI "why is CPU high?" for analysis

---

### `/ram`

**Purpose**: Memory usage details

**Usage**:
```
/ram
```

**Shows**:
- Total RAM
- Used RAM
- Available RAM
- Usage percentage
- Swap usage (if configured)

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

### `/disk`

**Purpose**: Disk usage for all mounted filesystems

**Usage**:
```
/disk
```

**Shows**:
- All mounted filesystems
- Total, used, free space
- Usage percentage
- Mount points

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
Free: 1.2 TB
```

**Alert**: Warning if any disk >80% full

---

### `/temps`

**Purpose**: System temperature sensors

**Usage**:
```
/temps
```

**Shows**:
- CPU temperature
- Disk temperatures (if available)
- GPU temperature (if available)
- Other sensors

**Example**:
```
🌡 Temperature Sensors

CPU: 52°C
Disk 1 (sda): 38°C
Disk 2 (sdb): 40°C
GPU: 45°C
```

**Note**: Requires `lm-sensors` on bare metal

---

### `/network`

**Purpose**: Network statistics

**Usage**:
```
/network
```

**Shows**:
- Download/upload speeds
- Total bytes sent/received
- Active connections
- IP addresses (including Tailscale)

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
```

---

### `/uptime`

**Purpose**: System uptime

**Usage**:
```
/uptime
```

**Shows**:
- Days, hours, minutes since last boot
- Boot time timestamp

**Example**:
```
⏱ System Uptime

5 days, 3 hours, 42 minutes

Started: 2026-05-13 05:18:00
```

---

### `/health`

**Purpose**: Overall system health score

**Usage**:
```
/health
```

**Shows**:
- Health score (0-100)
- Health status
- Detected issues

**Example**:
```
🟢 System Health: Good (85/100)

Issues:
⚠️ Disk /volume1 at 78% capacity
⚠️ Service nginx not running
```

**Scoring**:
- 90-100: Excellent ✅
- 70-89: Good 🟢
- 50-69: Fair 🟡
- 30-49: Poor 🟠
- 0-29: Critical 🔴

---

### `/smart`

**Purpose**: SMART drive health data

**Usage**:
```
/smart
```

**Shows**:
- All detected drives
- SMART health status
- Temperature
- Power-on hours
- Reallocated sectors

**Example**:
```
💿 Drive Health (SMART)

/dev/sda (WD Red 4TB)
Status: PASSED ✅
Temp: 38°C
Power On: 12,450 hours
Reallocated Sectors: 0

/dev/sdb (Seagate 2TB)
Status: PASSED ✅
Temp: 40°C
Power On: 8,200 hours
```

**Requirements**: `smartmontools` installed

---

### `/drives`

**Purpose**: List all drives

**Usage**:
```
/drives
```

**Shows**:
- Drive device names
- Capacity
- Model
- Serial numbers

**Example**:
```
💿 System Drives

sda: WD Red 4TB
    Model: WDC WD40EFRX
    Serial: WD-WCC...

sdb: Seagate 2TB
    Model: ST2000DM008
    Serial: ZDH...
```

---

## Docker Management

### `/docker` or `/containers`

**Purpose**: List all Docker containers

**Usage**:
```
/docker
/containers
```

**Shows**:
- Container names
- Status (running/stopped)
- CPU and memory usage
- Uptime

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

**Purpose**: Restart a Docker container

**Usage**:
```
/restart <container_name>
```

**Parameters**:
- `container_name` - Name or ID of container

**Example**:
```
You: /restart nginx
Bot: ⚙️ Restarting nginx...
     ✅ Container nginx restarted successfully!
```

**Tips**:
- Use exact container name from `/docker`
- Case-sensitive
- Requires confirmation for some containers

---

### `/stop <container>`

**Purpose**: Stop a running container

**Usage**:
```
/stop <container_name>
```

**Example**:
```
You: /stop nginx
Bot: ⏸ Stopping nginx...
     ✅ Container nginx stopped successfully!
```

**Warning**: Only stops container, doesn't remove it

---

### `/start <container>`

**Purpose**: Start a stopped container

**Usage**:
```
/start <container_name>
```

**Example**:
```
You: /start redis
Bot: ▶️ Starting redis...
     ✅ Container redis started successfully!
```

---

### `/logs <container> [lines]`

**Purpose**: View container logs

**Usage**:
```
/logs <container_name>
/logs <container_name> 50
/logs <container_name> 100
```

**Parameters**:
- `container_name` - Container name
- `lines` - Number of lines (default: 50, max: 200)

**Example**:
```
You: /logs nginx 20
Bot: 📋 Last 20 lines from nginx:
     
     2026-05-18 09:00:01 GET /api/status 200
     2026-05-18 09:00:05 GET /health 200
     ...
```

**Tips**:
- Use for troubleshooting
- Check after restart
- Look for errors or warnings

---

## File System

### `/files`

**Purpose**: Browse default document path

**Usage**:
```
/files
```

**Shows**: Contents of `DOCUMENT_PATH` from `.env`

**Example**:
```
📁 /app/documents

Directories:
📁 IELTS
📁 Projects
📁 Books

Files:
1️⃣ readme.md (2.3 KB)
2️⃣ notes.txt (15 KB)
3️⃣ report.pdf (1.2 MB)
```

---

### `/ls [path]`

**Purpose**: List directory contents with numbered files

**Usage**:
```
/ls
/ls IELTS
/ls /absolute/path
```

**Parameters**:
- `path` - Directory path (optional)
  - No path = default document directory
  - Relative path = relative to documents
  - Absolute path = full path (requires permission)

**Examples**:
```
# List default directory
You: /ls
Bot: 📁 /app/documents
     [Shows numbered file list]

# List subdirectory
You: /ls IELTS
Bot: 📁 /app/documents/IELTS
     [Shows numbered file list]

# Absolute path (root access)
You: /ls /var/log
Bot: 📁 /var/log
     [Shows numbered file list]
```

**Output Format**:
- Directories listed first (no numbers)
- Files numbered with emojis (1️⃣-🔟)
- Files 11+ use plain numbers

**Tips**:
- Files stay cached for 10 minutes
- Use numbers for `/download` command
- Relative paths are easier

---

### `/download <number>`

**Purpose**: Download file from last `/ls` command

**Usage**:
```
/download <number>
```

**Parameters**:
- `number` - File number from `/ls` output

**Example**:
```
You: /ls
Bot: 📁 /app/documents
     1️⃣ report.pdf (1.2 MB)
     2️⃣ notes.txt (5 KB)

You: /download 1
Bot: 📤 Sending report.pdf...
     [File sent via Telegram]
```

**Limitations**:
- Files cached for 10 minutes
- Run `/ls` again if cache expired
- Max file size: 50MB (Telegram limit)

---

### `/uploadfile [subfolder]`

**Purpose**: Upload file to NAS (requires root access)

**Usage**:
```
/uploadfile
/uploadfile IELTS
/uploadfile Projects/Current
```

**Parameters**:
- `subfolder` - Target subfolder (optional)
  - No subfolder = documents root
  - Relative path = under documents

**Example**:
```
You: /uploadfile IELTS
Bot: 📥 Ready to receive file for /app/documents/IELTS
     Send a file now...

[You send file]

Bot: ✅ File uploaded successfully!
     📁 /app/documents/IELTS/yourfile.pdf
```

**Requirements**:
- Active root session (`/rootlogin`)
- Write permissions on target directory

**Supported**: All file types

---

### `/find <filename>`

**Purpose**: Search for files across allowed paths

**Usage**:
```
/find <filename>
```

**Parameters**:
- `filename` - Full or partial filename

**Examples**:
```
# Search for exact name
You: /find report.pdf
Bot: 🔍 Found 3 results:
     📄 /documents/reports/report.pdf
     📄 /documents/2025/report.pdf
     📄 /backups/report.pdf

# Partial match
You: /find .pdf
Bot: 🔍 Found 42 results:
     [First 20 shown]
```

**Tips**:
- Searches recursively
- Case-insensitive
- Use wildcards: `*.pdf`, `report*`

---

### `/tree [path]`

**Purpose**: Show directory tree structure

**Usage**:
```
/tree
/tree Projects
```

**Parameters**:
- `path` - Directory to visualize (optional)

**Example**:
```
You: /tree
Bot: 📁 /app/documents
     ├── 📁 IELTS
     │   ├── 📄 reading.pdf
     │   └── 📄 writing.pdf
     ├── 📁 Projects
     │   ├── 📁 Current
     │   └── 📁 Archive
     └── 📄 readme.md
```

**Limits**: Max 3 levels deep, 50 items

---

### `/storage`

**Purpose**: Storage usage analysis

**Usage**:
```
/storage
```

**Shows**:
- Total storage
- Used space
- Largest directories
- File type breakdown

**Example**:
```
💾 Storage Analysis

Total: 4.0 TB
Used: 2.8 TB (70%)
Available: 1.2 TB

Largest Directories:
1. /volume1/media (1.5 TB)
2. /volume1/backups (800 GB)
3. /volume1/documents (300 GB)
```

---

## Service Management

### `/services`

**Purpose**: List system services

**Usage**:
```
/services
```

**Shows**:
- Common services (nginx, docker, ssh, etc.)
- Status (active/inactive)
- Auto-start setting

**Example**:
```
⚙️ System Services

nginx ✅ Active
docker ✅ Active
ssh ✅ Active
postgresql ⏸ Inactive
```

**Note**: Only shows common services, not all

---

### `/restart_service <service>`

**Purpose**: Restart a system service

**Usage**:
```
/restart_service <service_name>
```

**Example**:
```
You: /restart_service nginx
Bot: ⚙️ Restarting nginx service...
     ✅ Service nginx restarted successfully!
```

**Requirements**: Sudo permissions

---

### `/reboot`

**Purpose**: Reboot the system

**Usage**:
```
/reboot
```

**Safety**:
- Requires confirmation
- 30-second countdown
- Can cancel during countdown

**Example**:
```
You: /reboot
Bot: ⚠️ System Reboot Requested
     
     This will restart the entire system.
     Are you sure?
     
     [Yes] [No]
```

**Warning**: Bot will be offline during reboot!

---

### `/shutdown`

**Purpose**: Shutdown the system

**Usage**:
```
/shutdown
```

**Safety**:
- Requires confirmation
- 30-second countdown
- Can cancel

**Warning**: System will power off. Requires physical access to restart!

---

## AI Assistant

### `/ask <question>`

**Purpose**: Ask questions about your documents (RAG)

**Usage**:
```
/ask <your question>
```

**Features**:
- Searches indexed documents
- Semantic understanding
- Context from 10 previous messages
- Citations included

**Examples**:
```
You: /ask What are the IELTS speaking test criteria?
Bot: Based on your documents, IELTS speaking is 
     assessed on four criteria:
     1. Fluency and Coherence
     2. Lexical Resource
     ...
     Source: ielts-speaking-guide.pdf

# Follow-up works naturally
You: Tell me more about the first one
Bot: [Remembers context about criteria]
```

**Requirements**:
- Documents indexed with `/index`
- Relevant content in documents

---

### `/chat <message>`

**Purpose**: General AI conversation

**Usage**:
```
/chat <message>
```

**Difference from `/ask`**:
- Doesn't search documents
- Uses OpenAI knowledge only
- Faster responses
- Lower cost

**Example**:
```
You: /chat Explain Docker networking basics
Bot: Docker networking allows containers to 
     communicate...
```

---

### `/summarize <topic>`

**Purpose**: Summarize documents about a topic

**Usage**:
```
/summarize <topic>
```

**Example**:
```
You: /summarize IELTS writing task 2 tips
Bot: Here's a summary of writing task 2 tips 
     from your documents:
     
     1. Plan your essay (5 mins)
     2. Clear thesis statement...
```

---

### `/explain <term>`

**Purpose**: Explain a term from your documents

**Usage**:
```
/explain <term or concept>
```

**Example**:
```
You: /explain cohesion in IELTS
Bot: Based on your IELTS materials, cohesion 
     refers to...
```

---

### `/analyze <text>`

**Purpose**: Deep analysis using reasoning model

**Usage**:
```
/analyze <text or question>
```

**Uses**: O3-mini model (advanced reasoning)

**Best for**:
- Complex problems
- Multi-step reasoning
- Technical analysis
- Strategic planning

**Example**:
```
You: /analyze Should I upgrade my NAS storage 
     or add more RAM first?
Bot: [Detailed reasoning and recommendation]
```

**Note**: Slower and more expensive than `/ask`

---

### `/think <question>`

**Purpose**: Complex reasoning (alias for `/analyze`)

**Usage**:
```
/think <question>
```

**Same as `/analyze`**, different command name

---

### `/websearch <query>`

**Purpose**: Search the internet with AI summary

**Usage**:
```
/websearch <query>
```

**Features**:
- Searches current web
- AI-powered summary
- Includes sources

**Example**:
```
You: /websearch latest Docker security best 
     practices 2026
Bot: Here's what I found about Docker security 
     in 2026:
     
     1. Use rootless containers...
     2. Implement image signing...
     
     Sources:
     - docker.com/security
     - [Additional links]
```

**Requirements**: Serper or Tavily API key

---

### `/index`

**Purpose**: Index or re-index documents for RAG

**Usage**:
```
/index
```

**Process**:
1. Scans `DOCUMENT_PATH`
2. Extracts text from files
3. Creates embeddings
4. Stores in ChromaDB

**Duration**: Varies by document count
- 10 documents: ~30 seconds
- 100 documents: ~5 minutes
- 1000+ documents: ~30+ minutes

**Example**:
```
You: /index
Bot: 📊 Starting document indexing...
     Found 42 documents
     
     [Progress updates]
     
     ✅ Indexing complete!
     Indexed: 42 documents
     Total chunks: 385
```

**When to run**:
- First time setup
- After adding new documents
- If search results seem stale

---

### `/clear`

**Purpose**: Clear conversation history

**Usage**:
```
/clear
```

**Effect**:
- Removes last 10 messages from context
- Fresh conversation start
- Reduces API token usage

**Example**:
```
You: /clear
Bot: 🗑 Conversation history cleared!
     Starting fresh conversation.
```

**Tip**: Use when switching topics

---

## Root Access

### `/rootlogin <password>`

**Purpose**: Activate temporary root access

**Usage**:
```
/rootlogin <password>
```

**Parameters**:
- `password` - The `ROOT_PASSWORD` from `.env`

**Duration**: 30 minutes

**Grants**:
- Access to all file system paths
- Ability to use `/ssh` command
- File upload permission

**Example**:
```
You: /rootlogin MySecurePass123!
Bot: 🔓 Root Access Granted
     
     You now have full file system access 
     for 30 minutes.
     
     ⚠️ All actions are logged.
```

**Security**:
- All actions logged
- Auto-expires after 30 minutes
- Failed attempts logged

---

### `/rootstatus`

**Purpose**: Check root session status

**Usage**:
```
/rootstatus
```

**Shows**:
- Session active/inactive
- Time remaining
- Started/expires time

**Example**:
```
You: /rootstatus
Bot: 🔓 Root Session Active
     
     Started: 09:00:00
     Expires: 09:30:00
     Time Remaining: 18m 35s
     
     ⚠️ All actions are being logged.
```

---

### `/rootlogout`

**Purpose**: End root session early

**Usage**:
```
/rootlogout
```

**Example**:
```
You: /rootlogout
Bot: 🔒 Root Session Ended
     
     File access restored to normal permissions.
```

**Tip**: Good security practice to logout when done

---

### `/ssh <command>`

**Purpose**: Execute shell commands

**Usage**:
```
/ssh <command>
```

**Requirements**: Active root session

**Parameters**:
- `command` - Shell command to execute

**Examples**:
```
# List files (defaults to documents folder)
You: /ssh ls -la
Bot: ✅ Exit Code: 0
     Output:
     total 42
     drwxr-xr-x  5 user user  4096 May 18 09:00 .
     ...

# Check disk space
You: /ssh df -h
Bot: [Shows disk usage]

# Docker commands
You: /ssh docker ps
Bot: [Shows containers]

# Create directory
You: /ssh mkdir test
Bot: ✅ Directory created
```

**Default Directory**: `/app/documents` (for relative commands)

**Timeout**: 60 seconds

**Security**: All commands logged

---

## Command Tips

### Natural Follow-ups

The bot remembers your last 10 messages:

```
You: /cpu
Bot: CPU Usage: 90%

You: why is it so high?
Bot: [Analyzes and explains based on CPU context]
```

### Command Shortcuts

Some commands have aliases:
- `/docker` = `/containers`
- `/think` = `/analyze`

### Batch Operations

Reference previous command outputs:

```
You: /docker
Bot: [Lists: nginx, postgres, redis (stopped)]

You: start the last one
Bot: [Starts redis container]
```

### Error Recovery

If command fails:
1. Check `/help` for correct syntax
2. Verify permissions (root access if needed)
3. Check logs: `/logs <container>` for Docker
4. Try `/clear` and repeat

### Performance Tips

- Use `/clear` when switching topics (saves tokens)
- `/index` only when documents change
- Use `/ask` for documents, `/chat` for general questions
- `/download` files expire after 10 min, re-run `/ls` if needed

---

## Quick Reference Card

**Most Used Commands**:
```
/status       - System overview
/cpu /ram     - Resource usage
/docker       - List containers
/ls           - List files
/ask          - Document Q&A
/help         - Show all commands
```

**Emergency Commands**:
```
/health       - System health check
/restart      - Restart container
/reboot       - Reboot system
```

**Security Commands**:
```
/rootlogin    - Elevate access
/rootlogout   - Drop access
/rootstatus   - Check access
```

---

**Need more details?** Check specific feature guides:
- [[AI and RAG|AI-and-RAG]] for AI features
- [[File Management|File-Management]] for file operations
- [[Docker Management|Docker-Management]] for containers
- [[Root Access and SSH|Root-Access-and-SSH]] for elevated access
