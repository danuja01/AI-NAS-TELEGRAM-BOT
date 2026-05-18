# File Management

Complete guide to secure file operations via the NAS Telegram AI Assistant.

---

## Overview

Manage files on your NAS directly from Telegram with robust security:
- Browse directories with numbered file lists
- Download files by number
- Upload files (root access)
- Search for files
- View directory trees
- Analyze storage usage
- Path validation and restrictions

---

## File Commands

### `/files`

Browse the default document directory.

**Shows**: Contents of `DOCUMENT_PATH` from configuration.

---

### `/ls [path]`

List directory contents with numbered files for easy downloading.

**Usage**:
```
/ls                 # List default directory
/ls DANUJA          # List subdirectory (relative)
/ls /absolute/path  # List absolute path (requires permission)
```

**Example**:
```
📁 /app/documents

Directories:
📁 IELTS
📁 Projects

Files:
1️⃣ report.pdf (1.2 MB)
2️⃣ notes.txt (5 KB)
3️⃣ guide.docx (450 KB)
```

**Features**:
- Directories shown first (no numbers)
- Files numbered 1️⃣-🔟, then plain numbers
- File cache valid for 10 minutes
- Relative paths resolved to documents folder

---

### `/download <number>`

Download a file from the last `/ls` command.

**Usage**:
```
/ls
/download 1    # Downloads first file from list
```

**Example**:
```
You: /ls
Bot: [Shows numbered file list]

You: /download 1
Bot: 📤 Sending report.pdf...
     [File sent via Telegram]
```

**Limitations**:
- File list cached for 10 minutes
- Max file size: 50MB (Telegram limit)
- Must run `/ls` first

---

### `/uploadfile [subfolder]`

Upload a file to your NAS (requires root access).

**Usage**:
```
/uploadfile              # Upload to documents root
/uploadfile IELTS        # Upload to subfolder
/uploadfile Projects/Current  # Upload to nested folder
```

**Process**:
```
You: /uploadfile IELTS
Bot: 📥 Ready to receive file for /app/documents/IELTS
     Send a file now...

[You send file in Telegram]

Bot: ✅ File uploaded successfully!
     📁 /app/documents/IELTS/yourfile.pdf
```

**Requirements**:
- Active root session (`/rootlogin`)
- Write permissions on target directory
- Target folder must exist

**Supported**: All file types

---

### `/find <filename>`

Search for files across allowed paths.

**Usage**:
```
/find report.pdf         # Exact name
/find *.pdf              # Wildcard
/find report             # Partial match
```

**Example**:
```
🔍 Found 3 results:

📄 /documents/reports/report.pdf
📄 /documents/2025/report.pdf
📄 /backups/report.pdf
```

**Features**:
- Case-insensitive search
- Recursive through subdirectories
- Limited to `ALLOWED_PATHS`

---

### `/tree [path]`

Display directory tree structure.

**Usage**:
```
/tree              # Tree of current directory
/tree Projects     # Tree of subdirectory
```

**Example**:
```
📁 /app/documents
├── 📁 IELTS
│   ├── 📄 reading.pdf
│   └── 📄 writing.pdf
├── 📁 Projects
│   ├── 📁 Current
│   └── 📁 Archive
└── 📄 readme.md
```

**Limits**: Max 3 levels deep, 50 items total

---

### `/storage`

Analyze storage usage across filesystems.

**Shows**:
- Total and used space
- Largest directories
- Usage breakdown

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

## Security Features

### Path Validation

All file operations are validated against `ALLOWED_PATHS`.

**Configuration** (`.env`):
```env
ALLOWED_PATHS=/home/user/documents,/home/user/projects
```

**What happens**:
- Paths outside `ALLOWED_PATHS` are blocked
- Attempts to access blocked paths are logged
- Root sessions bypass restrictions (full `/` access)

### Path Traversal Protection

Protection against directory traversal attacks:
- `../` sequences blocked
- Symlinks validated
- Absolute paths normalized

**Blocked attempts**:
```
/ls ../../etc/passwd  # Blocked
/ls /etc              # Blocked (not in ALLOWED_PATHS)
```

### Root Access Integration

With active root session (`/rootlogin`):
- Access to all paths (`/`)
- Upload permissions
- `/ssh` command access
- All actions logged

---

## File Cache System

### How It Works

When you run `/ls`, files are cached in memory for 10 minutes:

1. **First call**: `/ls DANUJA`
   - Scans directory
   - Numbers files
   - Stores in cache

2. **Follow-up**: `/download 3`
   - Retrieves file #3 from cache
   - Sends via Telegram

3. **Expiration**: After 10 minutes
   - Cache cleared
   - Run `/ls` again to refresh

### Cache Benefits

- Fast downloads (no re-scan)
- Consistent numbering
- Low system impact

---

## Best Practices

### Organizing Files

**Good structure**:
```
documents/
├── Work/
│   ├── Projects/
│   └── Meetings/
├── Personal/
│   ├── Finance/
│   └── Health/
└── Archive/
    └── 2025/
```

**Benefits**:
- Easier navigation
- Better organization
- Faster searches

### File Naming

**Good**:
- `project-proposal-2026-05.pdf`
- `meeting-notes-team-sync.md`
- `budget_Q2_2026.xlsx`

**Avoid**:
- `untitled.pdf`
- `doc1.pdf`
- `New Document (2).docx`

### Security Practices

1. **Limit ALLOWED_PATHS**
   - Only necessary directories
   - Don't use root `/` unless needed

2. **Use root access sparingly**
   - Login only when needed
   - Logout when done: `/rootlogout`

3. **Review uploads**
   - Verify uploaded files
   - Check for unexpected files

4. **Monitor logs**
   - Review access attempts
   - Check for suspicious activity

---

## Use Cases

### Daily File Access

```
# Morning: Check new files
/ls
/download 1

# Add notes
[Edit locally, then...]
/rootlogin <password>
/uploadfile
[Send file]
/rootlogout
```

### Document Management

```
# Find all PDFs
/find *.pdf

# Check specific folder
/ls Reports/2026

# Download multiple files
/download 1
/download 2
/download 3
```

### Storage Maintenance

```
# Check space
/storage

# Find large files
/tree Projects

# Clean up
/rootlogin <password>
/ssh rm -rf old_backups/*
/rootlogout
```

---

## Working with Paths

### Relative vs Absolute

**Relative** (resolved to `DOCUMENT_PATH`):
```
/ls DANUJA        → /app/documents/DANUJA
/ls Work/Projects → /app/documents/Work/Projects
```

**Absolute** (requires permission):
```
/ls /var/log     → /var/log (if in ALLOWED_PATHS or root)
/ls /etc         → Blocked (not in ALLOWED_PATHS)
```

### Path Tips

- Use relative paths when possible
- Tab completion doesn't work (it's Telegram!)
- Case-sensitive on Linux
- Use `/find` if unsure of location

---

## Troubleshooting

### Access Denied Errors

**Error**: `Path '/app/DANUJA' is not within allowed paths`

**Solutions**:
1. Use relative paths: `/ls DANUJA` not `/ls /app/DANUJA`
2. Check `ALLOWED_PATHS` in `.env`
3. Use root access if needed: `/rootlogin`

### Download Failed

**Error**: File download fails or times out

**Solutions**:
1. Check file size (< 50MB)
2. Run `/ls` again (cache expired)
3. Verify file still exists
4. Check network connection

### Upload Failed

**Error**: Upload rejected or fails

**Solutions**:
1. Verify root access active: `/rootstatus`
2. Check target directory exists
3. Verify write permissions
4. Check disk space: `/disk`

### File Not Found

**Error**: `/find` returns no results

**Solutions**:
1. Check spelling (case-sensitive)
2. Verify file in `ALLOWED_PATHS`
3. Use wildcard: `/find *partial*`
4. Check with `/tree` to browse

---

## Advanced Features

### Batch Downloads

Download multiple files efficiently:

```
/ls

You: /download 1
You: /download 2
You: /download 3

[All files sent in succession]
```

### Upload to Nested Folders

```
/uploadfile Projects/2026/Q2
[Creates path if root has permissions]
```

### Search Patterns

```
/find *.pdf              # All PDFs
/find report*            # Files starting with "report"
/find *2026*             # Files containing "2026"
```

---

**Related**:
- [[Commands Reference|Commands-Reference]] - All file commands
- [[Root Access and SSH|Root-Access-and-SSH]] - Elevated access
- [[Security]] - Security model
- [[Configuration Guide|Configuration-Guide]] - Path settings
