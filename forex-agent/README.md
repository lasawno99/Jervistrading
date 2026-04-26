# forex-agent

A long-running Python worker that uses Claude (Anthropic) to monitor forex markets, place **paper-only** trades on an OANDA practice account, and report via Telegram. It is a pure worker (no HTTP listener) and is designed for Railway with zero rework.

> **Paper-only by design.** Live trading is impossible without editing `app/guardrails.py` *and* setting `OANDA_ENVIRONMENT=practice`. Don't.

---

## Architecture

```
┌─────────────────────────┐         ┌──────────────────────────────────┐
│  Emergent dashboard     │         │  Railway worker (this repo)      │
│  (React + FastAPI)      │         │                                  │
│  read-only views        │         │  APScheduler ──tick──► Agent     │
└───────────┬─────────────┘         │       ▲          (Claude Sonnet) │
            │                       │       │                  │       │
            │                       │       │                  │ tools │
            │   shared (optional)   │   Telegram /commands     ▼       │
            ▼                       │                  ┌───────────────┐│
      ┌──────────┐                  │                  │ OANDA practice││
      │ MongoDB  │ ◄─── v2 ─────────┤                  │ Tavily news   ││
      └──────────┘                  │                  │ Telegram poll ││
                                    └──────────────────┴───────────────┘
```

- **Claude Sonnet** (default `claude-sonnet-4-6`) drives the tool loop. The LLM only proposes orders.
- **`app/guardrails.py`** decides whether each order is allowed. The LLM cannot bypass it.
- **APScheduler** (`AsyncIOScheduler`) runs three jobs in the same event loop as the Telegram updater: morning brief, alert scan, and a 60s health heartbeat.
- **Telegram polling only** — no webhooks, so the worker is portable across hosts.

---

## Quickstart (local)

```bash
git clone <this repo>
cd forex-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your real keys
python -m app.main
```

You should see structured JSON logs on stdout, ending with `services_started`. Send `/start` to your bot in Telegram to confirm the polling loop is alive.

Run tests:

```bash
pytest -q
```

---

## Environment variables

All required. The process refuses to start if any are missing. Set these in Railway → Variables, **never** in committed code.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | yes | — | From console.anthropic.com |
| `ANTHROPIC_MODEL` | yes | `claude-sonnet-4-6` | |
| `OANDA_API_TOKEN` | yes | — | Practice token from oanda.com |
| `OANDA_ACCOUNT_ID` | yes | — | Practice account id |
| `OANDA_ENVIRONMENT` | yes | `practice` | **Hard-locked to `practice`. Other values rejected at boot.** |
| `TAVILY_API_KEY` | yes | — | From tavily.com |
| `TELEGRAM_BOT_TOKEN` | yes | — | From @BotFather |
| `TELEGRAM_CHAT_ID` | yes | — | Your chat id (from @userinfobot). Allowlist is enforced. |
| `TRADING_MODE` | yes | `paper` | **Hard-locked to `paper`. Other values rejected at boot.** |
| `INSTRUMENTS` | yes | `EUR_USD,GBP_USD,XAU_USD` | Comma-separated |
| `SCHEDULE_CRON` | yes | `*/15 9-21 * * 1-5` | UTC, drives the alert-scan job |
| `MAX_POSITION_UNITS` | yes | `1000` | Per-order cap |
| `DAILY_LOSS_LIMIT_PCT` | yes | `2` | Net loss as % of UTC-day starting NAV |

Notes on ones that bite:
- `OANDA_API_TOKEN` (not `OANDA_API_KEY`).
- `TELEGRAM_CHAT_ID` (not `TELEGRAM_USER_ID`). It's the numeric chat id where the bot will message and from which it will accept commands.

---

## Railway deploy steps

1. **Push this repo to GitHub.**
2. **In Railway**, "New Project" → "Deploy from GitHub repo" → pick this repo.
3. Railway detects the `Dockerfile` and uses `railway.json` for the deploy config (start command: `python -m app.main`, restart on failure up to 10x).
4. Open **Settings → Variables** and add every variable from the table above. Do not commit a `.env` to GitHub.
5. Click **Deploy**. Watch the logs — you should see `services_started` and a `✅ Forex agent online.` Telegram message.
6. Redeploy is graceful: Railway sends `SIGTERM`, the worker stops the scheduler and Telegram updater cleanly, then exits.

> Screenshot placeholders: <!-- railway-create-project --> <!-- railway-vars --> <!-- railway-deploy-logs -->

---

## Telegram setup

1. Message [@BotFather](https://t.me/BotFather), `/newbot`, choose a name. Save the bot token.
2. Message [@userinfobot](https://t.me/userinfobot) to get your numeric chat id.
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in Railway → Variables.
4. After deploy, send `/start` to your bot.

The worker's allowlist drops every message from any chat id other than `TELEGRAM_CHAT_ID`. There is no group-chat support in v1.

---

## OANDA setup

1. Open a free practice account at [oanda.com](https://oanda.com).
2. In the practice account dashboard, **Manage API Access** → generate a personal access token.
3. Copy the **practice account id** (looks like `101-001-XXXXXXX-001`).
4. Set `OANDA_API_TOKEN` and `OANDA_ACCOUNT_ID` in Railway → Variables.
5. `OANDA_ENVIRONMENT` must stay as `practice`. Anything else fails at boot.

---

## Slash command reference

| Command | What it does |
|---|---|
| `/start` | Auth check + lists available commands |
| `/brief` | Runs an on-demand market brief (no trading; same as morning brief) |
| `/positions` | Lists open paper positions and unrealized P&L |
| `/balance` | Practice account balance, NAV, and unrealized P&L |
| `/kill on` / `/kill off` | Toggle the global kill switch — short-circuits all guardrails |
| `/schedules` | Lists active scheduled jobs and next run times |
| `/jarvis [text]` | Free-form chat with the agent (full tool access) |

`/brief` and `/jarvis` dispatch their work as background asyncio tasks so a slow Claude call (5–10s on tool-heavy turns) never blocks the Telegram polling loop.

### 5-prompt verification demo

After deploy, send these to your bot in order:

1. `/start`
2. `/balance`
3. `/positions`
4. `/brief`
5. `/jarvis what's your read on EUR_USD right now?`

If all five reply within ~30s, you're good.

---

## Scheduled jobs

| Job | Schedule | Action |
|---|---|---|
| Morning brief | `0 8 * * *` UTC daily | Runs the agent in dry-run; reports a market summary, no orders |
| Alert scan | `SCHEDULE_CRON` env (default `*/15 9-21 * * 1-5`) | Runs the agent live; may place paper orders |
| Health check | every 60s | Logs heartbeat: kill-switch state, halted-today, recent orders count |

---

## Guardrails (the part that matters)

Every order, no matter how confident the LLM is, runs through `app/guardrails.py:check_order` before hitting OANDA. Order matters — cheapest checks first, manual override above all automated rules:

1. **Kill switch** active → reject. (`/kill on`)
2. `TRADING_MODE != "paper"` → reject.
3. `OANDA_ENVIRONMENT != "practice"` → reject.
4. Already halted earlier this UTC day → reject.
5. `stop_loss is None` → reject. **Every order requires a stop-loss.**
6. `units <= 0` or `units > MAX_POSITION_UNITS` → reject.
7. Daily net loss ≥ `DAILY_LOSS_LIMIT_PCT` of the UTC-day starting NAV → halt the rest of the day; fire one Telegram alert (`🛑 Daily loss limit hit, trading halted.`).
8. \>5 orders in any rolling 60s window → reject.

Every rule has a corresponding test in `tests/test_guardrails.py`. CI runs them on every push.

---

## Going live (don't, yet)

This codebase is paper-only by **design**, not by config. To flip to live you'd have to:

1. Edit `app/guardrails.py` and remove rules 2 and 3 (the `paper`/`practice` checks).
2. Edit `app/tools/oanda_tool.py` and remove the `environment != "practice"` constructor reject and the `api-fxpractice.oanda.com` host assertion.
3. Set `OANDA_ENVIRONMENT=live`.

**You should not do this without weeks of paper-trading evidence and an honest review of your daily P&L distribution.** A profitable backtest is not a profitable trading account.

---

## Troubleshooting

**Bot not responding to `/start`.**
- Check Railway logs for `services_started` and `Forex agent online.` If missing, look for a config validation error at the top of the logs.
- Verify `TELEGRAM_BOT_TOKEN` is correct and the bot wasn't revoked in @BotFather.
- Verify `TELEGRAM_CHAT_ID` matches your numeric id from @userinfobot. Messages from other chat ids are silently dropped (you'll see `unauthorized_chat` in logs).

**"Guardrail rejected my order."**
- Look in logs for `guardrail_rejected` — the `reason` field tells you which rule fired.
- Common: missing stop-loss (LLM forgot), units over `MAX_POSITION_UNITS`, daily loss limit already triggered today, or `/kill on` is active.
- Quick check: send `/kill` (no arg) to see kill-switch state, `/balance` for daily P&L, `/schedules` for next run.

**Railway redeploy.**
- Railway sends `SIGTERM`. Worker stops scheduler → Telegram updater → application, then exits. Logs end with `shutdown_complete`.
- New deploy boots fresh. `GuardrailState` is in-memory only (no DB in v1), so kill-switch state and daily-halt status reset across redeploys. If you want persistence, add MongoDB in v2.

**Anthropic 429 / overloaded.**
- The agent surfaces the error in logs and as a Telegram message. Wait a few minutes and re-send `/brief` or `/jarvis`.

**OANDA 401 / 403.**
- Token is wrong, expired, or pointing at live. Regenerate in the practice dashboard and update Railway → Variables.

---

## What this repo does NOT do (intentionally)

- No web UI, dashboard, FastAPI server, or HTTP endpoint of any kind.
- No live OANDA endpoint (`api-fxtrade`). Hard-locked to practice at the client layer.
- No Telegram webhooks. Polling only.
- No database in v1. Logs to stdout.
- No MT4 / MT5 / ZeroMQ / MetaApi / Cloudflare Tunnel / Windows VPS scaffolding.
- No LLM other than Claude.
