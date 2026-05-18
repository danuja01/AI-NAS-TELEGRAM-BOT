# Security

Comprehensive security guide for the NAS Telegram AI Assistant.

---

## Security Model

### Multi-Layer Security

The bot implements defense-in-depth with multiple security layers:

1. **Authentication**: User whitelist
2. **Authorization**: Path restrictions
3. **Rate Limiting**: Command throttling
4. **Audit Logging**: Complete activity logs
5. **Confirmation Dialogs**: Dangerous operations
6. **Root Access Control**: Password-protected elevated access

---

## Authentication

### User Whitelist

Only users in `ALLOWED_USER_IDS` can interact with the bot.

**Configuration** (`.env`):
```env
ALLOWED_USER_IDS=123456789,987654321
```

**What Happens**:
- Unauthorized users are silently ignored
- No error messages (prevents information disclosure)
- Attempts logged for monitoring

**Adding Users**:
1. Get their Telegram user ID (from @userinfobot)
2. Add to `ALLOWED_USER_IDS` in `.env`
3. Restart bot

**Removing Users**:
1. Remove ID from `ALLOWED_USER_IDS`
2. Restart bot
3. Active sessions invalidated immediately

---

## Authorization

### Path Restrictions

File system access limited to `ALLOWED_PATHS`.

**Configuration**:
```env
ALLOWED_PATHS=/app/documents,/app/data
```

**Protection**:
- Directory traversal attacks (`../`)
- Symbolic link exploitation
- Absolute path escaping
- Access outside allowed paths

**Bypass**: Only via root access (password-protected)

---

## Rate Limiting

### Command Throttling

**Limit**: 10 commands per minute per user

**Purpose**:
- Prevent abuse
- Limit API costs
- Protect system resources
- Mitigate brute force

**When Exceeded**:
```
⚠️ Rate Limit Exceeded

Please wait before sending more commands.
Limit: 10 commands per minute
```

**Implementation**: Rolling window, resets every minute

---

## Audit Logging

### What's Logged

**All user activity**:
- Commands executed
- Login attempts (success/failure)
- Root access (login/logout)
- SSH commands
- File operations
- API calls
- Errors and exceptions

**Log Locations**:
- Application log: `logs/bot.log`
- Database: `data/bot.db` (commands table)

**Log Rotation**:
- Max size: 10MB per file
- Keep: 3 files (30MB total)
- Automatic rotation

### Log Review

**View recent activity**:
```bash
tail -100 logs/bot.log
```

**Search for user activity**:
```bash
grep "user_id: 123456789" logs/bot.log
```

**Find root access**:
```bash
grep -i "root" logs/bot.log
```

**Check failed attempts**:
```bash
grep -i "failed\|error\|denied" logs/bot.log
```

### Log Monitoring

**Set up daily review**:
```bash
# Cron job to email daily summary
0 9 * * * grep "$(date +%Y-%m-%d)" /path/to/logs/bot.log | mail -s "Bot Activity" you@email.com
```

**Alerts for sensitive operations**:
- Root logins
- Failed authentication
- Path access denials
- Multiple rate limit hits

---

## Root Access Security

### Password Protection

**Strong Password Requirements**:
- Minimum 12 characters
- Mix of character types
- Not reused from other services
- Changed quarterly

**Configuration**:
```env
ROOT_PASSWORD=YourVerySecurePassword123!
```

**Never**:
- Commit to version control
- Share with unauthorized users
- Use common passwords
- Reuse from other systems

### Session Management

**Session Properties**:
- 30-minute timeout
- Auto-expiration
- User-specific
- Logged activity

**Manual Logout**: Always logout when done
```
/rootlogout
```

### SSH Command Safety

**All commands logged**:
```log
2026-05-18 09:15:30 - WARNING - User 123456789 executing SSH command: rm -rf /data/old
```

**Best Practices**:
- Verify commands before running
- Use `--dry-run` when available
- Backup before destructive operations
- Review command output

---

## API Key Protection

### Environment Variables

**Never hardcode API keys**:

❌ **Bad**:
```python
api_key = "sk-1234567890abcdef"
```

✅ **Good**:
```python
api_key = os.getenv("OPENAI_API_KEY")
```

### .env File Security

**Protect .env file**:

```bash
# Set restrictive permissions
chmod 600 .env

# Add to .gitignore
echo ".env" >> .gitignore

# Never commit
git add .gitignore
git commit -m "Ignore .env file"
```

**Verify not in repo**:
```bash
git log --all --full-history -- .env
# Should return nothing
```

### API Key Rotation

**Regular rotation schedule**:
- OpenAI key: Every 3-6 months
- Search API keys: Every 6-12 months
- Telegram bot token: Only if compromised
- ROOT_PASSWORD: Every 3 months

**Rotation process**:
1. Generate new key at provider
2. Update `.env`
3. Restart bot
4. Verify functionality
5. Revoke old key at provider

### Key Compromise Response

If API key exposed:

1. **Immediately revoke** at provider
2. **Generate new key**
3. **Update `.env`**
4. **Restart bot**
5. **Review usage** for abuse
6. **Check logs** for unauthorized activity
7. **Rotate other keys** if shared environment

---

## Confirmation Dialogs

### Dangerous Operations

Commands that require confirmation:
- `/reboot` - System reboot
- `/shutdown` - System shutdown
- Container operations on critical services

**Example**:
```
You: /reboot

Bot: ⚠️ System Reboot Requested
     
     This will restart the entire system.
     Bot will be offline during reboot.
     
     Are you sure?
     
     [Yes] [No]
```

**Timeout**: Confirmations expire after 60 seconds

---

## Network Security

### Telegram API

**Built-in security**:
- HTTPS encrypted
- Telegram's infrastructure
- Bot token authentication

**Bot Token Security**:
- Keep token secret
- Never log token
- Regenerate if exposed (via @BotFather)

### Docker Socket

If mounting Docker socket:

**Security implications**:
- Container can control Docker daemon
- Equivalent to root access
- Necessary for Docker management features

**Mitigation**:
- Run with least privilege
- Audit socket access
- Monitor Docker commands
- Consider Docker-in-Docker alternatives

### Internet Search APIs

**Data exposure**:
- Search queries sent to third party (Serper/Tavily)
- Consider privacy implications
- Review API provider privacy policy

**Mitigation**:
- Use for non-sensitive queries only
- Disable if privacy-critical
- Self-host search if needed

---

## Docker Security

### Container Security

**Best practices**:
1. **Use official base images**
   ```dockerfile
   FROM python:3.11-slim  # Official image
   ```

2. **Don't run as root**
   ```dockerfile
   USER appuser
   ```

3. **Minimal image**
   - Only necessary packages
   - Multi-stage builds
   - Remove build tools

4. **Scan for vulnerabilities**
   ```bash
   docker scan nas-telegram-bot:latest
   ```

### Docker Compose Security

**Resource limits**:
```yaml
resources:
  limits:
    cpus: '2.0'
    memory: 4G
```

**Read-only where possible**:
```yaml
volumes:
  - ./documents:/app/documents:ro  # Read-only
```

**Network isolation**:
```yaml
networks:
  - isolated_network
```

---

## Incident Response

### Suspicious Activity Detection

**Red flags**:
- Multiple failed login attempts
- Unusual root access patterns
- Commands at odd hours
- Access to sensitive paths
- High rate limit hits
- Unknown user IDs in logs

### Response Steps

1. **Immediate**:
   - Review recent logs
   - Check active sessions
   - Revoke compromised credentials

2. **Investigate**:
   - Identify affected systems
   - Determine attack vector
   - Assess damage scope

3. **Contain**:
   - Disable compromised accounts
   - Change all passwords
   - Update `ALLOWED_USER_IDS`
   - Restart bot

4. **Recover**:
   - Restore from backups if needed
   - Verify system integrity
   - Update security measures

5. **Learn**:
   - Document incident
   - Improve security
   - Update procedures

---

## Security Checklist

### Initial Setup

- [ ] Strong `ROOT_PASSWORD` (12+ chars)
- [ ] `.env` not committed to Git
- [ ] `.env` permissions set (chmod 600)
- [ ] `ALLOWED_USER_IDS` contains only trusted users
- [ ] `ALLOWED_PATHS` minimally scoped
- [ ] API keys are valid and unique
- [ ] Telegram bot token secured

### Regular Maintenance

- [ ] Review logs weekly
- [ ] Rotate passwords quarterly
- [ ] Update `ALLOWED_USER_IDS` as needed
- [ ] Check for unauthorized access attempts
- [ ] Update bot and dependencies
- [ ] Review and clean up root access logs
- [ ] Test backup restoration

### Monthly Security Review

- [ ] Audit all user access
- [ ] Review configuration files
- [ ] Check for exposed secrets
- [ ] Update dependencies
- [ ] Review API usage
- [ ] Backup audit logs
- [ ] Test incident response

---

## Security Best Practices Summary

1. **Authentication**
   - Whitelist users only
   - Strong passwords
   - Regular rotation

2. **Authorization**
   - Minimal path access
   - Root access only when needed
   - Logout after use

3. **Monitoring**
   - Review logs regularly
   - Alert on suspicious activity
   - Track all root access

4. **API Keys**
   - Never commit to repo
   - Rotate regularly
   - Revoke if compromised

5. **System**
   - Keep updated
   - Backup regularly
   - Test recovery procedures

6. **Network**
   - Use HTTPS/TLS
   - Limit exposed services
   - Monitor traffic

---

**Related**:
- [[Root Access and SSH|Root-Access-and-SSH]] - Elevated access security
- [[Configuration Guide|Configuration-Guide]] - Security settings
- [[File Management|File-Management]] - Path security
