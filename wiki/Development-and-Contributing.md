# Development and Contributing

Guide for developers who want to contribute to the NAS Telegram AI Assistant.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Git
- Docker (optional, for testing)
- Text editor/IDE

### Development Setup

1. **Fork and clone**:
   ```bash
   git clone https://github.com/your-username/nas-telegram-bot.git
   cd nas-telegram-bot/BOT
   ```

2. **Create virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure `.env`**:
   ```bash
   cp .env.example .env
   # Edit .env with your test credentials
   ```

5. **Run bot**:
   ```bash
   python bot.py
   ```

---

## Project Structure

```
BOT/
├── bot.py                 # Main entry point
├── config.py              # Configuration
├── requirements.txt       # Dependencies
├── Dockerfile             # Docker image
├── docker-compose.yml     # Docker Compose config
├── commands/              # Command handlers
│   ├── basic.py
│   ├── monitoring.py
│   ├── docker_cmds.py
│   ├── filesystem.py
│   ├── ai_cmds.py
│   ├── service.py
│   └── root_cmds.py
├── services/              # Business logic
│   ├── system_monitor.py
│   ├── docker_service.py
│   ├── smart_monitor.py
│   ├── file_service.py
│   └── service_manager.py
├── ai/                    # AI components
│   ├── gpt_client.py
│   ├── rag_engine.py
│   ├── conversation_history.py
│   ├── search_engine.py
│   ├── document_loader.py
│   ├── embeddings.py
│   └── ollama_client.py
├── database/              # Database layer
│   ├── models.py
│   └── memory.py
├── monitoring/            # Alerts
│   ├── health_checker.py
│   └── alerts.py
├── utils/                 # Utilities
│   ├── security.py
│   ├── formatters.py
│   ├── logger.py
│   ├── root_session.py
│   └── file_cache.py
├── data/                  # Persistent data
├── logs/                  # Log files
└── documents/             # Test documents
```

---

## Code Style

### Python Style Guide

Follow [PEP 8](https://pep8.org/):

```python
# Good
def calculate_health_score(cpu: float, ram: float) -> int:
    """Calculate system health score."""
    score = 100
    if cpu > 80:
        score -= 20
    return score

# Use type hints
# Docstrings for functions
# Clear variable names
```

### Formatting

```bash
# Use black for formatting
pip install black
black .

# Use flake8 for linting
pip install flake8
flake8 .
```

---

## Adding New Commands

### 1. Create Command Handler

In appropriate file under `commands/`:

```python
from telegram import Update
from telegram.ext import ContextTypes
from utils.security import require_auth, rate_limit
from database.memory import save_command

@require_auth
@rate_limit
async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mycommand - Description here."""
    user_id = update.effective_user.id
    
    try:
        # Your logic here
        result = do_something()
        
        # Send response
        await update.message.reply_text(f"Result: {result}")
        
        # Save to database
        await save_command(user_id, '/mycommand', result)
        
    except Exception as e:
        logger.error(f"Error in my_command: {e}", exc_info=True)
        await update.message.reply_text(f"Error: {e}")
```

### 2. Register Command

In `bot.py`:

```python
from commands.yourfile import my_command

def main():
    # ...
    application.add_handler(CommandHandler("mycommand", my_command))
```

### 3. Update Help Text

In `commands/basic.py`, add to help message:

```python
help_msg = """
...
**Your Category**
`/mycommand` - Description of command
...
"""
```

### 4. Test Command

```bash
python bot.py
# In Telegram: /mycommand
```

---

## Adding New AI Models

### In `ai/gpt_client.py`:

```python
async def call_new_model(prompt: str) -> str:
    """Call new AI model."""
    try:
        response = await client.chat.completions.create(
            model="new-model-name",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=4000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error calling new model: {e}")
        raise
```

---

## Testing

### Manual Testing

1. Run bot locally
2. Test commands via Telegram
3. Check logs for errors
4. Verify database entries

### Adding Tests

Create `tests/` directory:

```python
import pytest
from services.system_monitor import get_cpu_stats

def test_get_cpu_stats():
    stats = get_cpu_stats()
    assert 'usage' in stats
    assert 0 <= stats['usage'] <= 100
```

Run tests:
```bash
pytest tests/
```

---

## Database Migrations

If changing database schema:

1. Update `database/models.py`
2. Create migration script
3. Test locally
4. Document in PR

Example migration:
```python
async def migrate_add_new_table():
    db = await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS new_table (
            id INTEGER PRIMARY KEY,
            data TEXT
        )
    """)
    await db.commit()
    await db.close()
```

---

## Contributing Guidelines

### Before Submitting PR

- [ ] Code follows PEP 8
- [ ] Added docstrings
- [ ] Tested locally
- [ ] Updated documentation
- [ ] No hardcoded credentials
- [ ] Error handling added
- [ ] Logging implemented

### PR Process

1. **Fork repo**
2. **Create feature branch**:
   ```bash
   git checkout -b feature/my-feature
   ```
3. **Make changes**
4. **Commit**:
   ```bash
   git commit -m "Add: new feature description"
   ```
5. **Push**:
   ```bash
   git push origin feature/my-feature
   ```
6. **Create PR** on GitHub

### Commit Message Format

```
Type: Brief description

Longer description if needed

- Bullet points for details
- Reference issues: #123
```

**Types**: Add, Fix, Update, Refactor, Docs, Test

---

## Release Process

1. Update version in `config.py`
2. Update CHANGELOG.md
3. Create git tag: `git tag v1.2.0`
4. Push: `git push --tags`
5. Create GitHub release
6. Build Docker image
7. Update documentation

---

## Need Help?

- Check [[Architecture]] for design
- Review existing code for patterns
- Ask in GitHub Discussions
- Open issue for bugs

---

**Thank you for contributing!**
