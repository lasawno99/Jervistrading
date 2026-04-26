# PRD — `forex-agent` (Railway worker)

## Original problem statement

"Build a Python application called `forex-agent`. It is a long-running worker (NOT a web app) that uses an LLM to monitor forex markets, place paper trades on an OANDA practice account, and send updates via Telegram. It must be deployable to Railway with zero rework."

## Non-negotiable rules

- Paper trading only. No live path. No MT4/MT5/Windows VPS/Cloudflare Tunnel.
- OANDA practice environment only (`api-fxpractice.oanda.com`).
- Telegram via long-polling (no webhooks).
- All secrets from `os.environ`.
- Guardrails run in deterministic Python, outside the LLM.

## Architecture (v1)

- Pure Python worker (no HTTP listener) — distinct from the JARVIS dashboard which lives in `/app/backend` + `/app/frontend` and stays on Emergent.
- Single asyncio event loop hosts both `python-telegram-bot` (polling) and `APScheduler` (`AsyncIOScheduler`).
- Slow LLM work dispatches via `asyncio.create_task` so the polling loop is never blocked.
- Lazy daily-balance reset: starting NAV captured on first order of each new UTC day.
- Three scheduled jobs: morning brief 08:00 UTC, alert scan via `SCHEDULE_CRON`, 60s health-check heartbeat.

## Tech stack

Python 3.11, anthropic 0.97, oandapyV20 0.7.2, tavily-python, python-telegram-bot 21.7, APScheduler 3.10, structlog, python-dotenv, pytest.

## Slash commands

`/start`, `/brief`, `/positions`, `/balance`, `/kill on|off`, `/schedules`, `/jarvis [text]`. Allowlist enforced via `TELEGRAM_CHAT_ID`.

## Guardrails (8 rules, all tested)

1. Kill switch active → reject
2. `TRADING_MODE != "paper"` → reject
3. `OANDA_ENVIRONMENT != "practice"` → reject
4. Already halted earlier this UTC day → reject
5. `stop_loss is None` → reject
6. `units <= 0` or `units > MAX_POSITION_UNITS` → reject
7. Daily net loss ≥ `DAILY_LOSS_LIMIT_PCT` → halt rest of day, fire one Telegram alert
8. \>5 orders in any 60s window → reject

## Status

**v1 complete (2026-04-26).** 10/10 tests passing. Boot smoke test passes against real Anthropic/OANDA/Telegram APIs.

## What's implemented

- `app/config.py`, `app/guardrails.py`, `app/agent.py` (Anthropic tool loop), `app/main.py` (APScheduler + Telegram + handlers + SIGTERM shutdown).
- Tools: `oanda_tool.py` (locked to practice), `news_tool.py` (Tavily), `telegram_tool.py`. Stubs: `email_tool.py`, `calendar_tool.py`.
- `Dockerfile`, `railway.json`, GitHub Actions test workflow, `.env.example`, `.gitignore`.
- `README.md` with quickstart, Railway steps, env table, slash command reference, troubleshooting, going-live warning.

## Backlog (P1)

- User fills real `TAVILY_API_KEY` and `TELEGRAM_CHAT_ID` in Railway → Variables.
- User stops or token-rotates the JARVIS Telegram bot (currently polling same token in `/app/backend`) before deploy. Two pollers on one token → 409 Conflict.
- Push to GitHub, connect Railway, deploy.
- Run 5-prompt verification demo from Telegram: `/start`, `/balance`, `/positions`, `/brief`, `/jarvis what's your read on EUR_USD?`.

## Backlog (P2)

- MongoDB v2 for persistent guardrail state (kill switch + daily halt survives redeploys).
- Shared state with the Emergent JARVIS dashboard via the same Mongo.
- Real RSS news scout (currently Tavily only).
- Crypto exchanges (Binance/Bybit) integration.

## Files

```
/app/forex-agent/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── agent.py
│   ├── config.py
│   ├── guardrails.py
│   ├── tools/
│   │   ├── oanda_tool.py
│   │   ├── news_tool.py
│   │   ├── telegram_tool.py
│   │   ├── email_tool.py        (stub)
│   │   └── calendar_tool.py     (stub)
│   └── prompts/system.md
├── tests/test_guardrails.py     (10 passing)
├── Dockerfile, railway.json, requirements.txt
├── .env.example, .gitignore
├── .github/workflows/test.yml
└── README.md
```
