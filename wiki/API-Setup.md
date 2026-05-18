# API Setup Guide

Complete guide to obtaining and configuring all API keys needed for the NAS Telegram AI Assistant.

---

## Required APIs

### 1. Telegram Bot Token

**Required for**: Bot to function

**How to get**:

1. Open Telegram
2. Search for and message [@BotFather](https://t.me/BotFather)
3. Send `/newbot`
4. Choose a name for your bot (e.g., "My NAS Assistant")
5. Choose a username (must end in "bot", e.g., "mynasbot" or "my_nas_bot")
6. Copy the token provided (format: `123456789:ABCdefGHI...`)

**Example conversation**:
```
You: /newbot
BotFather: Alright, a new bot. How are we going to call it?

You: My NAS Assistant
BotFather: Good. Now let's choose a username for your bot.

You: my_nas_assistant_bot
BotFather: Done! Your bot token is:
           123456789:ABCdefGHIjklMNOpqrsTUVwxyz-1234567

           Keep your token secure!
```

**Configure**:
```env
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz-1234567
```

**Cost**: Free

---

### 2. Telegram User ID

**Required for**: User authentication

**How to get**:

1. Open Telegram
2. Search for and message [@userinfobot](https://t.me/userinfobot)
3. It will immediately reply with your user ID
4. Copy the number

**Example**:
```
You: [Start chat with @userinfobot]
Bot: Your User ID: 123456789
```

**Configure**:
```env
ALLOWED_USER_IDS=123456789
```

**Multiple users**:
```env
ALLOWED_USER_IDS=123456789,987654321,555444333
```

**Cost**: Free

---

### 3. OpenAI API Key

**Required for**: All AI features (RAG, chat, analysis)

**How to get**:

1. Go to [platform.openai.com](https://platform.openai.com)
2. Sign up or log in
3. Go to [API keys page](https://platform.openai.com/api-keys)
4. Click "Create new secret key"
5. Name it (e.g., "NAS Bot")
6. Copy the key immediately (shown only once!)
7. Save it securely

**Important**: 
- Key starts with `sk-proj-` or `sk-`
- Never share or commit to Git
- Cannot be retrieved later, only regenerated

**Configure**:
```env
OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890
```

**Cost**: 
- Pay-as-you-go pricing
- ~$5-50/month typical usage
- Set billing limits at [platform.openai.com/account/billing](https://platform.openai.com/account/billing)
- Free trial credits for new accounts

**Pricing**:
- GPT-5.4-Nano: $0.15-0.60 per 1M tokens
- O3-Mini: $3-12 per 1M tokens

---

## Optional APIs

### 4. Serper API (Web Search)

**Required for**: `/websearch` command

**How to get**:

1. Go to [serper.dev](https://serper.dev)
2. Click "Get API Key" or "Sign Up"
3. Sign up with Google/GitHub or email
4. Go to [Dashboard](https://serper.dev/dashboard)
5. Copy your API key

**Configure**:
```env
SERPER_API_KEY=abc123def456ghi789jkl012mno345pqr678
```

**Cost**:
- Free tier: 2,500 searches/month
- Pro: $50/month for 10,000 searches
- [Pricing details](https://serper.dev/pricing)

---

### 5. Tavily API (Web Search Alternative)

**Required for**: `/websearch` command (alternative to Serper)

**How to get**:

1. Go to [tavily.com](https://tavily.com)
2. Click "Get Started" or "Sign Up"
3. Create account
4. Go to [API Keys](https://app.tavily.com/api-keys)
5. Copy your API key

**Configure**:
```env
TAVILY_API_KEY=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
```

**Note**: Bot tries Serper first, then Tavily as fallback

**Cost**:
- Free tier: 1,000 searches/month
- Pro: $100/month for 10,000 searches
- [Pricing details](https://tavily.com/pricing)

---

### 6. Ollama (Local AI - Optional)

**Required for**: Local AI fallback (offline capabilities)

**How to setup**:

1. Install Ollama:
   ```bash
   # Linux/WSL
   curl -fsSL https://ollama.ai/install.sh | sh
   
   # Mac
   brew install ollama
   ```

2. Start Ollama:
   ```bash
   ollama serve
   ```

3. Pull a model:
   ```bash
   ollama pull llama2
   ```

4. Configure bot:
   ```env
   OLLAMA_URL=http://localhost:11434/api/generate
   ```

**Cost**: Free (runs locally)

**Requirements**:
- 8GB+ RAM recommended
- ~4GB disk per model
- Good CPU/GPU for speed

**Use case**: Fallback when OpenAI unavailable or for privacy

---

## Configuration Example

Complete `.env` file with all APIs:

```env
# ===== REQUIRED =====

# Telegram Bot (from @BotFather)
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz-1234567

# OpenAI (from platform.openai.com)
OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890

# Your Telegram User ID (from @userinfobot)
ALLOWED_USER_IDS=123456789

# ===== OPTIONAL =====

# Web Search APIs
SERPER_API_KEY=abc123def456ghi789jkl012mno345pqr678
TAVILY_API_KEY=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

# Local AI (Ollama)
OLLAMA_URL=http://localhost:11434/api/generate

# Root Access Password
ROOT_PASSWORD=YourSecurePassword123!

# ===== AI MODELS =====
DEFAULT_MODEL=gpt-5.4-nano
THINKING_MODEL=o3-mini
FALLBACK_MODEL=gpt-4o-mini

# ===== PATHS =====
DOCUMENT_PATH=/app/documents
ALLOWED_PATHS=/app/documents,/app/data
```

---

## Testing Your APIs

### Test Telegram Bot

```bash
# Start bot
python bot.py
# or
docker-compose up

# In Telegram, message your bot:
/start
```

**Expected**: Welcome message

**If fails**: Check `TELEGRAM_TOKEN` and bot logs

### Test OpenAI API

```bash
# Test with curl
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Or in bot**:
```
/ask test
```

**Expected**: AI response

**If fails**: Check API key validity and credits

### Test Web Search

```
/websearch test query
```

**Expected**: Search results with AI summary

**If fails**: Check Serper/Tavily API key

---

## Cost Management

### OpenAI Usage Monitoring

1. Go to [Usage Dashboard](https://platform.openai.com/usage)
2. View current month usage
3. Set up billing alerts
4. Review usage by day

**Setting Limits**:
1. Go to [Billing](https://platform.openai.com/account/billing/limits)
2. Set monthly budget limit
3. Set soft limit for warnings
4. Enable email notifications

### Reducing Costs

**Tips**:
1. Use `/clear` to reduce context length
2. Use appropriate models (nano for simple tasks)
3. Limit document collection size
4. Use `/chat` instead of `/ask` when documents not needed
5. Monitor usage regularly

### Estimated Monthly Costs

**Light Usage** (10 queries/day):
- OpenAI: $5-10
- Serper: Free (within limit)
- **Total**: ~$5-10/month

**Medium Usage** (50 queries/day):
- OpenAI: $20-40
- Serper: Free
- **Total**: ~$20-40/month

**Heavy Usage** (200 queries/day):
- OpenAI: $80-150
- Serper: May need paid tier
- **Total**: ~$100-200/month

---

## Security Best Practices

### API Key Storage

✅ **Do**:
- Store in `.env` file
- Set file permissions: `chmod 600 .env`
- Add `.env` to `.gitignore`
- Use environment variables

❌ **Don't**:
- Hardcode in source code
- Commit to Git
- Share publicly
- Reuse across projects

### Key Rotation

**Schedule**:
- OpenAI: Every 3-6 months
- Search APIs: Every 6-12 months
- Telegram token: Only if compromised
- ROOT_PASSWORD: Every 3 months

**Process**:
1. Generate new key at provider
2. Update `.env`
3. Restart bot
4. Verify working
5. Revoke old key

### Compromised Keys

If key exposed:
1. **Immediately revoke** at provider
2. Generate new key
3. Update `.env`
4. Restart bot
5. Review usage for abuse
6. Report if fraudulent charges

---

## Troubleshooting

### Invalid Telegram Token

**Error**: `telegram.error.InvalidToken`

**Solutions**:
- Check token format (no spaces)
- Verify with @BotFather
- Regenerate if needed

### OpenAI Authentication Error

**Error**: `AuthenticationError`

**Solutions**:
- Verify key starts with `sk-`
- Check key hasn't expired
- Verify account has credits
- Check [status.openai.com](https://status.openai.com)

### Rate Limit Errors

**Error**: `Rate limit exceeded`

**Solutions**:
- Wait a few minutes
- Upgrade OpenAI plan
- Use `/clear` to reduce context
- Check for runaway processes

### No Search Results

**Error**: Search fails or times out

**Solutions**:
- Verify Serper/Tavily key valid
- Check API credit balance
- Try alternative search API
- Check internet connection

---

**Related**:
- [[Configuration Guide|Configuration-Guide]] - All config options
- [[Installation]] - Setup instructions
- [[Troubleshooting]] - Common issues
