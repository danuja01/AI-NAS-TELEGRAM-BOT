# Troubleshooting

Common issues and solutions for the NAS Telegram AI Assistant.

---

## Bot Won't Start

### Issue: Bot fails to start

**Symptoms**:
- No response from bot
- Error in logs
- Container/process exits

**Solutions**:

1. **Check configuration**:
   ```bash
   cat .env | grep -v "^#" | grep .
   ```
   Verify all required variables are set

2. **Check logs**:
   ```bash
   tail -50 logs/bot.log
   # or Docker
   docker logs nas-telegram-bot
   ```

3. **Common errors**:
   - Missing `TELEGRAM_TOKEN`: Add to `.env`
   - Missing `OPENAI_API_KEY`: Add to `.env`
   - Invalid token format: Check for spaces/quotes
   - Permission denied: Check file permissions

4. **Verify dependencies**:
   ```bash
   pip list | grep telegram
   pip list | grep openai
   ```

---

## Bot Doesn't Respond

### Issue: Bot started but no response to messages

**Solutions**:

1. **Check ALLOWED_USER_IDS**:
   ```bash
   grep ALLOWED_USER_IDS .env
   ```
   Make sure your Telegram ID is included

2. **Get your correct ID**:
   - Message @userinfobot
   - Copy exact number
   - Update `.env`
   - Restart bot

3. **Check bot is running**:
   ```bash
   ps aux | grep bot.py
   # or Docker
   docker ps | grep nas-telegram-bot
   ```

4. **Test bot token**:
   ```bash
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
   ```

---

## AI Commands Fail

### Issue: /ask, /chat, /analyze commands fail

**Error messages**:
- "OpenAI API error"
- "Authentication failed"
- "Rate limit exceeded"

**Solutions**:

1. **Check API key**:
   ```bash
   grep OPENAI_API_KEY .env
   ```
   Verify starts with `sk-`

2. **Verify credits**:
   - Go to [platform.openai.com/usage](https://platform.openai.com/usage)
   - Check current balance
   - Add payment method if needed

3. **Check API status**:
   - Visit [status.openai.com](https://status.openai.com)

4. **Rate limits**:
   - Wait 60 seconds
   - Use `/clear` to reduce context
   - Upgrade OpenAI tier if needed

---

## No Documents Found (RAG)

### Issue: "I don't have information about that in your documents"

**Solutions**:

1. **Index documents**:
   ```
   /index
   ```

2. **Check document path**:
   ```bash
   ls -la $DOCUMENT_PATH
   ```

3. **Verify file formats**:
   - Supported: PDF, DOCX, TXT, MD
   - Check files aren't corrupted

4. **Check permissions**:
   ```bash
   chmod -R 755 documents/
   ```

5. **Review indexing logs**:
   ```bash
   grep "index" logs/bot.log
   ```

---

## Docker Commands Fail

### Issue: /docker, /restart commands don't work

**Error**: "Failed to connect to Docker"

**Solutions**:

**For Docker Deployment**:
1. Check `docker-compose.yml` has socket mount:
   ```yaml
   volumes:
     - /var/run/docker.sock:/var/run/docker.sock
   ```

2. Rebuild if needed:
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

**For Bare Metal**:
1. Add user to docker group:
   ```bash
   sudo usermod -aG docker $USER
   newgrp docker
   ```

2. Verify Docker running:
   ```bash
   docker ps
   ```

---

## SMART Commands Not Working

### Issue: /smart, /drives show "smartctl not found"

**Solutions**:

**Bare Metal**:
```bash
sudo apt install smartmontools
```

**Docker**:
1. Check Dockerfile includes:
   ```dockerfile
   RUN apt-get install -y smartmontools
   ```

2. Rebuild image:
   ```bash
   docker-compose build --no-cache
   docker-compose up -d
   ```

---

## Service Commands Fail

### Issue: /services, /restart_service don't work

**Error**: "systemctl not found" or "not available"

**Expected**: In Docker containers, systemctl isn't available

**Solutions**:
- This is normal in Docker
- Use host system for service management
- Or use `/docker` commands for containers

---

## Path Access Denied

### Issue: "Path not within allowed paths"

**Solutions**:

1. **Use relative paths**:
   ```
   /ls DANUJA        # Good
   /ls /app/DANUJA   # May be blocked
   ```

2. **Check ALLOWED_PATHS**:
   ```bash
   grep ALLOWED_PATHS .env
   ```

3. **Add path if needed**:
   ```env
   ALLOWED_PATHS=/app/documents,/app/data,/new/path
   ```

4. **Use root access**:
   ```
   /rootlogin <password>
   /ls /any/path
   ```

---

## High Memory Usage

### Issue: Bot using too much RAM

**Solutions**:

1. **Check resource usage**:
   ```bash
   docker stats nas-telegram-bot
   ```

2. **Clear conversation history**:
   ```
   /clear
   ```

3. **Reduce indexed documents**:
   - Remove unnecessary files
   - Archive old documents
   - Re-index

4. **Increase Docker limits**:
   Edit `docker-compose.yml`:
   ```yaml
   resources:
     limits:
       memory: 8G  # Increase from 4G
   ```

5. **Consider system upgrade**:
   - 4GB RAM minimum
   - 8GB+ recommended for large collections

---

## Database Locked

### Issue: "database is locked" errors

**Solutions**:

1. **Stop bot**:
   ```bash
   docker-compose down
   # or
   systemctl stop nas-telegram-bot
   ```

2. **Remove lock files**:
   ```bash
   rm -f data/bot.db-shm data/bot.db-wal
   ```

3. **Restart**:
   ```bash
   docker-compose up -d
   ```

---

## Telegram Conflict Error

### Issue: "terminated by other getUpdates request"

**Cause**: Multiple bot instances running

**Solutions**:

1. **Find all instances**:
   ```bash
   ps aux | grep bot.py
   docker ps -a | grep telegram
   ```

2. **Stop duplicates**:
   ```bash
   kill <pid>
   docker stop <container>
   ```

3. **Ensure only one runs**:
   - Either Docker OR bare metal
   - Not both simultaneously

---

## Upload/Download Issues

### Issue: File upload or download fails

**Solutions**:

**For Upload**:
1. Check root access active:
   ```
   /rootstatus
   ```

2. Verify write permissions

3. Check disk space:
   ```
   /disk
   ```

**For Download**:
1. Check file size < 50MB (Telegram limit)

2. Re-run `/ls` if cache expired

3. Verify file still exists

---

## Common Error Messages

### "Rate limit exceeded"

**Meaning**: Too many commands too fast

**Solution**: Wait 60 seconds

---

### "Invalid token"

**Meaning**: Telegram bot token wrong

**Solution**: Check `TELEGRAM_TOKEN` in `.env`

---

### "Authentication failed"

**Meaning**: OpenAI API key invalid

**Solution**: Verify `OPENAI_API_KEY`

---

### "Permission denied"

**Meaning**: File/directory not accessible

**Solutions**:
- Check permissions
- Use root access
- Verify path in `ALLOWED_PATHS`

---

### "Model not found"

**Meaning**: AI model name wrong

**Solution**: Check model names in `.env`:
```env
DEFAULT_MODEL=gpt-5.4-nano
THINKING_MODEL=o3-mini
```

---

## Debugging Tips

### Enable Debug Logging

Edit `.env`:
```env
LOG_LEVEL=DEBUG
```

Restart bot, check logs for detailed info.

### Check Logs in Real-Time

```bash
tail -f logs/bot.log
# or Docker
docker logs -f nas-telegram-bot
```

### Test Individual Components

**Test OpenAI**:
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Test Telegram**:
```bash
curl "https://api.telegram.org/bot$TELEGRAM_TOKEN/getMe"
```

**Test Docker**:
```bash
docker ps
```

---

## Getting Help

If issues persist:

1. **Check logs**: `tail -100 logs/bot.log`
2. **Review [[FAQ]]**
3. **Search GitHub Issues**
4. **Create new issue** with:
   - Error message
   - Relevant logs
   - Configuration (remove sensitive data!)
   - Steps to reproduce

---

**Related**:
- [[Installation]] - Setup issues
- [[Docker Deployment|Docker-Deployment]] - Docker issues
- [[Configuration Guide|Configuration-Guide]] - Config problems
- [[FAQ]] - Common questions
