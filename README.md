# Ambient Claude

A persistent, autonomous AI companion that runs 24/7 on Railway. Maintains memory across conversations, reachable via Telegram, with its own "thinking time" via an autonomy loop.

## Architecture

Single async Python process running three things cooperatively:

1. **Starlette/Uvicorn** — HTTP server receiving Telegram webhook POSTs
2. **python-telegram-bot Application** — processes updates, routes to handlers
3. **JobQueue (APScheduler)** — runs the autonomy loop on a configurable interval

## Setup

### 1. Create Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Save the bot token

### 2. Get Your Telegram User ID

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. Save the numeric ID it returns

### 3. Get Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com) → API Keys
2. Create a new key and save it

### 4. Deploy to Railway

1. Connect this repo to [Railway](https://railway.app)
2. Add a persistent volume mounted at `/data`
3. Set environment variables (see `.env.example`):
   - `TELEGRAM_BOT_TOKEN` — from BotFather
   - `ANTHROPIC_API_KEY` — from Anthropic console
   - `WEBHOOK_URL` — your Railway app URL (e.g. `https://your-app.railway.app`)
   - `ALLOWED_USER_IDS` — your Telegram user ID
4. Deploy

### 5. Local Development

```bash
# Copy and fill in environment variables
cp .env.example .env
source .env && export $(cut -d= -f1 .env)

# Install dependencies
pip install -r requirements.txt

# Run in polling mode (no webhook needed)
python main.py --polling
```

## Bot Commands

- `/start` — Welcome message
- `/memory` — View current memory state
- `/forget` — Clear current session

## Memory System

Five persistent memory files in `/data/memory/`:

| File | Purpose |
|------|---------|
| `identity.md` | Personality and values (seeded once) |
| `user_context.md` | Accumulated facts about the user |
| `conversation_summary.md` | Rolling 7-day conversation summaries |
| `active_threads.md` | Ongoing projects and topics |
| `queue.md` | Follow-ups, reminders, ideas |

Memory synthesis runs automatically when:
- A session times out (30 min of inactivity)
- Message threshold is reached (10 messages in a session)

## Autonomy Loop

Runs every 60 minutes (configurable). Two-phase process:

1. **Think** (Haiku, cheap) — review context, decide if action needed
2. **Act** (Sonnet, quality) — compose message if warranted

Triple-gated proactive messaging:
- Quiet hours (23:00–08:00 UTC)
- Cooldown (2h between proactive messages)
- Daily limit (3 messages/day)

Can also journal and update the queue without messaging.

## Cost Estimate

~$4-5/month at moderate use (10 messages/day, hourly autonomy):
- Conversations: ~$2-3 (Sonnet with prompt caching)
- Memory synthesis: ~$0.27 (Haiku, 30 sessions/month)
- Autonomy loop: ~$1.08 (Haiku, 720 cycles/month)
- Proactive messages: ~$0.36 (Sonnet, ~30 messages/month)

## Verification

1. Check `/health` returns 200
2. Message the bot — should respond with memory context loaded
3. Send several messages, wait 30 min, message again — should reference earlier conversation
4. Check logs for autonomy cycle entries every hour
5. Run `/memory` to inspect current memory state
6. Check `/data/workspace/journal/` for journal entries
