# Configuration Guide

Complete reference for configuring the NAS Telegram AI Assistant via environment variables.

---

## Table of Contents

1. [Configuration File](#configuration-file)
2. [Required Variables](#required-variables)
3. [AI Model Configuration](#ai-model-configuration)
4. [Security Settings](#security-settings)
5. [Path Configuration](#path-configuration)
6. [API Keys (Optional)](#api-keys-optional)
7. [Database Settings](#database-settings)
8. [Logging Configuration](#logging-configuration)
9. [Advanced Settings](#advanced-settings)
10. [Configuration Examples](#configuration-examples)

---

## Configuration File

All configuration is done through the `.env` file in the project root.

### Creating Your Configuration

```bash
# Copy the example file
cp .env.example .env

# Edit with your preferred editor
nano .env
# or
vim .env
# or
code .env
```

### Important Notes

- **Never commit `.env` to Git** - It contains sensitive credentials
- **No spaces around `=`** - Use `KEY=value`, not `KEY = value`
- **No quotes needed** - Unless value contains special characters
- **Comments start with `#`**
- **Changes require restart** - Restart bot after editing

---

## Required Variables

These variables MUST be set for the bot to work:

### TELEGRAM_TOKEN

**Description**: Your Telegram bot token from @BotFather

**Format**: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

**How to get**:
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot`
3. Follow prompts to create bot
4. Copy the token provided

**Example**:
```env
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz-1234567
```

**Common Issues**:
- Missing or invalid token → Bot won't start
- Spaces in token → Authentication fails
- Token regenerated → Update this value

---

### OPENAI_API_KEY

**Description**: Your OpenAI API key for AI features

**Format**: `sk-` followed by alphanumeric string

**How to get**:
1. Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Sign up or log in
3. Click "Create new secret key"
4. Copy the key immediately (shown only once!)

**Example**:
```env
OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890
```

**Cost Notes**:
- AI features use OpenAI API (paid service)
- Approximate costs: $0.15-$3 per million tokens
- Monitor usage at [platform.openai.com/usage](https://platform.openai.com/usage)

**Common Issues**:
- Invalid key → AI commands fail
- No credits → Rate limit errors
- Key leaked → Regenerate immediately!

---

### ALLOWED_USER_IDS

**Description**: Comma-separated list of Telegram user IDs who can use the bot

**Format**: One or more numeric user IDs

**How to get your ID**:
1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your user ID

**Examples**:
```env
# Single user
ALLOWED_USER_IDS=123456789

# Multiple users
ALLOWED_USER_IDS=123456789,987654321,555444333

# With comments (not in actual file)
ALLOWED_USER_IDS=123456789    # You
```

**Security Note**: Only users in this list can interact with the bot. Anyone else will be ignored.

---

## AI Model Configuration

Configure which OpenAI models to use for different tasks:

### DEFAULT_MODEL

**Description**: Primary model for general AI tasks

**Recommended**: `gpt-5.4-nano` or `gpt-4o-mini`

**Options**:
- `gpt-5.4-nano` - Fastest, cheapest, good for most tasks
- `gpt-4o-mini` - Balanced speed and quality
- `gpt-4o` - Higher quality, slower, more expensive

**Example**:
```env
DEFAULT_MODEL=gpt-5.4-nano
```

**Used for**:
- `/ask` command (document Q&A)
- `/chat` command
- `/summarize`, `/explain` commands

---

### THINKING_MODEL

**Description**: Advanced reasoning model for complex tasks

**Recommended**: `o3-mini`

**Options**:
- `o3-mini` - Advanced reasoning, slower but thorough
- `o1-mini` - Previous generation reasoning
- `gpt-4o` - Fallback option

**Example**:
```env
THINKING_MODEL=o3-mini
```

**Used for**:
- `/analyze` command
- `/think` command
- Complex problem solving

**Note**: Thinking models are more expensive but provide better reasoning.

---

### FALLBACK_MODEL

**Description**: Backup model if primary models fail

**Recommended**: `gpt-4o-mini`

**Example**:
```env
FALLBACK_MODEL=gpt-4o-mini
```

**When used**:
- Primary model returns error
- Rate limit exceeded
- Model not available

---

## Security Settings

### ROOT_PASSWORD

**Description**: Password for temporary elevated access

**Required for**: `/rootlogin`, `/ssh` commands

**Security Requirements**:
- Minimum 12 characters
- Mix of letters, numbers, symbols
- Don't use common passwords
- Don't reuse from other services

**Example**:
```env
ROOT_PASSWORD=MySecure!Password#2026
```

**What it grants**:
- Full file system access for 30 minutes
- Ability to execute shell commands via `/ssh`
- All actions are logged for audit

**Security Warning**: Choose a strong password! This grants significant system access.

---

### Rate Limiting

**Built-in**: 10 commands per minute per user

**Purpose**: Prevent abuse and API cost overruns

**Configurable**: Currently hardcoded, can be modified in `utils/security.py`

---

## Path Configuration

Configure file system access:

### DOCUMENT_PATH

**Description**: Default path for documents (RAG/AI Q&A)

**Examples**:
```env
# Bare metal
DOCUMENT_PATH=/home/user/documents

# NAS (Synology)
DOCUMENT_PATH=/volume1/documents

# NAS (QNAP)
DOCUMENT_PATH=/share/documents

# Docker (default)
DOCUMENT_PATH=/app/documents
```

**Used for**:
- `/index` command - Indexes documents here
- `/ask` command - Searches documents here
- `/files` command - Lists files here
- Default directory for `/ls` when no path given

---

### ALLOWED_PATHS

**Description**: Comma-separated paths users can access

**Security**: Users cannot access paths outside this list (unless root session active)

**Examples**:
```env
# Single path
ALLOWED_PATHS=/home/user/documents

# Multiple paths
ALLOWED_PATHS=/home/user/documents,/var/www,/opt/data

# Docker default
ALLOWED_PATHS=/app/documents,/app/data
```

**Important**:
- Must include `DOCUMENT_PATH`
- Use absolute paths
- No wildcards or regex

---

## API Keys (Optional)

### SERPER_API_KEY

**Description**: API key for Serper web search

**Required for**: `/websearch` command

**How to get**:
1. Go to [serper.dev](https://serper.dev)
2. Sign up (free tier: 2,500 searches/month)
3. Copy API key from dashboard

**Example**:
```env
SERPER_API_KEY=abc123def456ghi789jkl
```

**Optional**: Can use Tavily instead or skip web search feature

---

### TAVILY_API_KEY

**Description**: API key for Tavily web search

**Required for**: `/websearch` command (alternative to Serper)

**How to get**:
1. Go to [tavily.com](https://tavily.com)
2. Sign up (free tier: 1,000 searches/month)
3. Get API key

**Example**:
```env
TAVILY_API_KEY=tvly-xyz789abc123def456
```

**Note**: Bot will try Serper first, then Tavily if configured

---

### OLLAMA_URL

**Description**: URL for local Ollama AI server (optional fallback)

**Default**: `http://localhost:11434/api/generate`

**Purpose**: Use local AI when OpenAI unavailable or for privacy

**Setup**:
1. Install Ollama: [ollama.ai](https://ollama.ai)
2. Run model: `ollama run llama2`
3. Configure URL if non-default

**Example**:
```env
# Default
OLLAMA_URL=http://localhost:11434/api/generate

# Custom port
OLLAMA_URL=http://localhost:8080/api/generate

# Remote server
OLLAMA_URL=http://192.168.1.100:11434/api/generate
```

**When used**: Fallback when OpenAI unavailable

---

## Database Settings

### DATABASE_PATH

**Description**: Path to SQLite database file

**Default**: `./data/bot.db`

**Contains**:
- Conversation history
- Command logs
- Alert history
- User sessions

**Examples**:
```env
# Relative path (default)
DATABASE_PATH=./data/bot.db

# Absolute path
DATABASE_PATH=/var/lib/nas-bot/bot.db

# Docker
DATABASE_PATH=/app/data/bot.db
```

**Backup**: Important to back up regularly!

---

### CHROMA_PATH

**Description**: Path to ChromaDB vector database

**Default**: `./data/chroma_db`

**Contains**:
- Document embeddings
- Vector index for RAG
- Semantic search data

**Examples**:
```env
# Relative path (default)
CHROMA_PATH=./data/chroma_db

# Absolute path
CHROMA_PATH=/var/lib/nas-bot/chroma_db

# Docker
CHROMA_PATH=/app/data/chroma_db
```

**Note**: Can take significant disk space with many documents

---

## Logging Configuration

### LOG_LEVEL

**Description**: Logging verbosity level

**Options**:
- `DEBUG` - Very verbose, for development
- `INFO` - Normal operation details (default)
- `WARNING` - Only warnings and errors
- `ERROR` - Only errors
- `CRITICAL` - Only critical failures

**Example**:
```env
LOG_LEVEL=INFO
```

**Recommendation**: Use `INFO` for production, `DEBUG` for troubleshooting

---

### LOG_FILE

**Description**: Path to log file

**Default**: `./logs/bot.log`

**Example**:
```env
LOG_FILE=./logs/bot.log
```

**Log Rotation**: Automatically rotates at 10MB, keeps 3 files

**View logs**:
```bash
# Real-time
tail -f logs/bot.log

# Last 100 lines
tail -n 100 logs/bot.log

# Search for errors
grep ERROR logs/bot.log
```

---

## Advanced Settings

### CONVERSATION_HISTORY_LENGTH

**Description**: Number of recent messages to remember for context

**Default**: `10`

**Range**: 1-50 (higher = more context but more API cost)

**Example**:
```env
CONVERSATION_HISTORY_LENGTH=10
```

**Affects**:
- Follow-up questions
- Context awareness
- OpenAI API token usage

**Recommendation**: 10 is good balance of context and cost

---

## Configuration Examples

### Basic Home Setup

Minimal configuration for home use:

```env
# Required
TELEGRAM_TOKEN=123456789:ABCdefGHI...
OPENAI_API_KEY=sk-proj-abc123...
ALLOWED_USER_IDS=123456789

# Models (defaults work well)
DEFAULT_MODEL=gpt-5.4-nano
THINKING_MODEL=o3-mini
FALLBACK_MODEL=gpt-4o-mini

# Paths
DOCUMENT_PATH=/home/user/documents
ALLOWED_PATHS=/home/user/documents

# Root access
ROOT_PASSWORD=MySecure!Pass2026
```

### Docker Deployment

Configuration for Docker:

```env
# Required
TELEGRAM_TOKEN=123456789:ABCdefGHI...
OPENAI_API_KEY=sk-proj-abc123...
ALLOWED_USER_IDS=123456789

# Models
DEFAULT_MODEL=gpt-5.4-nano
THINKING_MODEL=o3-mini
FALLBACK_MODEL=gpt-4o-mini

# Docker paths (these are correct for container)
DOCUMENT_PATH=/app/documents
ALLOWED_PATHS=/app/documents,/app/data
DATABASE_PATH=/app/data/bot.db
CHROMA_PATH=/app/data/chroma_db

# Security
ROOT_PASSWORD=YourStrongPassword!123

# Optional: Web search
SERPER_API_KEY=your_key_here
```

### Synology NAS

Configuration for Synology NAS:

```env
# Required
TELEGRAM_TOKEN=123456789:ABCdefGHI...
OPENAI_API_KEY=sk-proj-abc123...
ALLOWED_USER_IDS=123456789,987654321  # Multiple users

# Paths (adjust volume name)
DOCUMENT_PATH=/volume1/documents
ALLOWED_PATHS=/volume1/documents,/volume1/backups,/volume1/media
DATABASE_PATH=/volume1/docker/nas-bot/data/bot.db
CHROMA_PATH=/volume1/docker/nas-bot/data/chroma_db

# Models
DEFAULT_MODEL=gpt-5.4-nano
THINKING_MODEL=o3-mini
FALLBACK_MODEL=gpt-4o-mini

# Security
ROOT_PASSWORD=SynologySecurePass!2026

# Web search
SERPER_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here

# Logging
LOG_LEVEL=INFO
LOG_FILE=/volume1/docker/nas-bot/logs/bot.log
```

### Multi-User Family Setup

For multiple family members:

```env
TELEGRAM_TOKEN=123456789:ABCdefGHI...
OPENAI_API_KEY=sk-proj-abc123...

# Multiple users (parent + kids)
ALLOWED_USER_IDS=123456789,234567890,345678901

# Shared document library
DOCUMENT_PATH=/home/shared/family-docs
ALLOWED_PATHS=/home/shared/family-docs,/home/shared/photos

# Strong password
ROOT_PASSWORD=FamilyNAS!Secure2026

# Models
DEFAULT_MODEL=gpt-5.4-nano
THINKING_MODEL=o3-mini
FALLBACK_MODEL=gpt-4o-mini

# Web search
SERPER_API_KEY=your_key_here
```

---

## Validation Checklist

Before running the bot, verify:

- [ ] `TELEGRAM_TOKEN` is valid (no spaces)
- [ ] `OPENAI_API_KEY` starts with `sk-`
- [ ] `ALLOWED_USER_IDS` contains your user ID
- [ ] `DOCUMENT_PATH` exists and is readable
- [ ] `ALLOWED_PATHS` includes `DOCUMENT_PATH`
- [ ] `ROOT_PASSWORD` is strong (12+ characters)
- [ ] No trailing spaces in values
- [ ] No quotes around values (unless needed)
- [ ] File is named exactly `.env` (not `.env.txt`)

---

## Troubleshooting

### Bot Won't Start

**Check logs**:
```bash
tail -f logs/bot.log
```

**Common issues**:
- Missing required variables
- Invalid API keys
- Syntax errors in `.env`

### Commands Fail

**Issue**: "Unauthorized" or no response

**Check**: `ALLOWED_USER_IDS` contains your Telegram user ID

### AI Commands Fail

**Issue**: OpenAI errors

**Check**:
- `OPENAI_API_KEY` is correct
- You have credits in OpenAI account
- Model names are correct

### Path Errors

**Issue**: "Path not allowed"

**Check**:
- `ALLOWED_PATHS` includes the path you're trying to access
- Paths are absolute (start with `/`)
- Paths exist and are readable

---

## Security Best Practices

1. **Never commit `.env` to version control**
   ```bash
   # Add to .gitignore
   echo ".env" >> .gitignore
   ```

2. **Use strong `ROOT_PASSWORD`**
   - 12+ characters
   - Mix of upper, lower, numbers, symbols
   - Unique (not used elsewhere)

3. **Limit `ALLOWED_USER_IDS`**
   - Only trusted users
   - Remove users who no longer need access

4. **Restrict `ALLOWED_PATHS`**
   - Minimum necessary paths
   - Don't use root `/` unless absolutely needed

5. **Rotate API keys regularly**
   - OpenAI keys every 3-6 months
   - Immediately if exposed

6. **Monitor usage**
   - Check OpenAI usage dashboard
   - Review bot logs for suspicious activity

7. **Backup configuration**
   ```bash
   # Backup .env (store securely!)
   cp .env .env.backup
   ```

---

## Next Steps

- Complete [[Installation]] or [[Docker Deployment|Docker-Deployment]]
- Set up [[API Setup|API-Setup]] for all keys
- Review [[Security]] best practices
- Explore [[Commands Reference|Commands-Reference]]

---

**Need help?** Check the [[Troubleshooting]] page or [[FAQ]].
