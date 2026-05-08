# PRD — JARVIS Trading System (monorepo)

## Services in this repo

| Service | Folder | Type | Role |
|---|---|---|---|
| JARVIS dashboard | `/app/backend` + `/app/frontend` | FastAPI + React (Emergent) | Command dashboard, runs the JARVIS Claude brain, 40 tools |
| forex-agent | `/app/forex-agent` | Python worker (Railway) | OANDA paper-trading bot, Telegram command bot (polls) |
| kronos-agent | `/app/kronos-agent` | Python worker (Railway) | Runs Kronos forecaster on OANDA candles, sends signals to Telegram |
| knowledge-arb | `/app/knowledge-arb` | Python worker (Railway) | Tavily + Claude narrative-emergence scout, sends signals |

All three Railway services share one Telegram bot (`@Jervistradebot`, token `8694341880:...`). Only **forex-agent** polls; kronos-agent and knowledge-arb are send-only → no 409 conflicts.

## forex-agent

See previous PRD entry. 8 deterministic guardrails, 10/10 tests passing, Claude Sonnet tool loop, APScheduler + Telegram polling, SIGTERM-graceful shutdown. Railway-ready.

**Status:** Pushed to GitHub. Live Railway deploy pending successful `TELEGRAM_BOT_TOKEN` paste (last reported error was `InvalidToken` from a fat-fingered paste — re-paste `8694341880:AAGAaezBo2t3ZlTyJSB6g-NreqkSkTiM9pk` in Railway Variables).

## kronos-agent (new 2026-05-03)

Signal-only Railway worker. No trading.

- **Model:** `NeoQuasar/Kronos-small` (~25M params, CPU-OK), `NeoQuasar/Kronos-Tokenizer-base`. Cached at `/hf_cache`.
- **Data:** OANDA practice candles (read-only), H1 granularity, 360h lookback, 24h forecast, 20 Monte-Carlo samples.
- **Signal logic:** `upside_prob = share of predicted steps above current price`; `vol_amp = predicted_std / historical_std`. Thresholds configurable (default 0.65 / 0.35, max_vol_amp 2.0).
- **Schedule:** `0 */4 * * 1-5` (every 4h Mon-Fri, UTC).
- **Output:** Telegram message with direction (BUY/SELL/SKIP), confidence (high/medium/low), price targets, upside probability, vol amplification.

Files: `config.py`, `oanda_fetch.py`, `kronos_client.py` (lazy-loads model), `signal.py`, `main.py`. `Dockerfile` clones the Kronos repo + adds `/app/Kronos` to PYTHONPATH. Lint clean.

## knowledge-arb (new 2026-05-03)

Signal-only Railway worker. Narrative-emergence scout.

- **Input:** `WATCHLIST` comma-separated topics.
- **Fetch:** Tavily news (24h window) + general (7d window), counts + titles + domains + snippets per topic.
- **Score:** Claude Sonnet 4.5 with strict JSON-only scoring prompt → `{stage, confidence 1-10, thesis, tickers (up to 5), risks}`.
- **Alert condition:** `stage ∈ {pre-emerging, emerging, breakout}` AND `confidence ≥ MIN_CONFIDENCE`. 7-day per-(topic, stage) cooldown.
- **Schedule:** `0 */6 * * *` (every 6h).

Files: `config.py`, `scout.py` (Tavily), `scorer.py` (Claude), `state.py` (cooldown), `main.py`. Lint clean. **Live smoke-tested** 2026-05-03 — Tavily + Claude both reached real APIs, scored "AI agents" as emerging/6, "small modular reactors" as pre-emerging/3, no alerts sent (below threshold — correct behavior).

## Deploy plan

Three separate Railway services, same GitHub repo, different Root Directories:

1. `forex-agent` — Root Directory `forex-agent`
2. `kronos-agent` — Root Directory `kronos-agent`
3. `knowledge-arb` — Root Directory `knowledge-arb`

Each service pastes its own env vars. Credentials can be shared (same Anthropic/Tavily/OANDA/Telegram keys).

## Backlog

- **P0 user action:** Push the two new services to GitHub (Save to GitHub button). Add two Railway services. Verify first alerts land in Telegram.
- **P1:** Move from single-bot-shared-token to per-service bots if signal channels get noisy.
- **P2:** Kronos upgrade to `Kronos-base` on a GPU host if medium-term accuracy matters more than cost.
- **P2:** knowledge-arb v2 — add Reddit + Google Trends as secondary signals beyond Tavily.
- **P2:** Shared MongoDB so kill-switch / cooldown / daily-halt state survives Railway redeploys.

## Dashboard Redesign — Premium Dark Fintech (2026-05-08, **NEW**)

Full visual overhaul of `/app/frontend` from cyan-Iron-Man-HUD aesthetic to a Framer-style premium dark fintech UI (Linear / Vercel / Arc-feel).

### What changed
- **New theme** (`src/index.css`): obsidian #050505 background, glassmorphic white/[0.02] cards with white/10 borders, subtle aura gradients (`--jv-aura-1` cyan, `--jv-aura-2` violet). Up=#00ff85, Down=#ff3b6e. Fonts: Outfit (heading) / Manrope (sans) / JetBrains Mono (mono). Replaced cyan scanlines with subtle grain only.
- **New JARVIS Orb** (`src/components/JarvisOrb.jsx`): CSS-only — layered radial-gradients + spinning conic-gradient rings + framer-motion breathing. No SVGs/images. State-aware (idle / listening / thinking).
- **New Broker Hero widget** (`src/components/panels/BrokerHeroPanel.jsx`): hero number (Total Wealth = NAV + Locked Profits), animated CountUp, glowing DoD badge, breakdown grid (Live NAV / Locked Profits / Open Positions / Margin Used), live indicator. Auto-refreshes every 15s.
- **New backend endpoint** `GET /api/broker/summary` (`backend/server.py`): unified payload — OANDA NAV/balance/unrealized/margin + locked profits sum from MongoDB collection `profit_locks` + day-over-day delta from `nav_snapshots` (auto-upserted on every call).
- **Refactored shells**: `Panel.jsx` (glassmorphic, no traffic-light dots, framer-motion entrance), `CommandPalette.jsx` (floating glassmorphic pill at bottom), `App.js` (cleaner header, broker hero front-and-center, orb below, asymmetric 3-12 sidebar grid).
- **Dependency added**: `framer-motion@12.38.0`.

### Data flow for the broker widget
- Real-time NAV polled from OANDA Practice via `oanda_client.get_account()`.
- `nav_snapshots` collection seeds today's row on first hit; tomorrow the DoD badge fills in automatically.
- `profit_locks` collection is empty for now; jarvis-synth Railway worker can POST events to it to make Locked Profits live.

### Verified working
- Backend: `curl /api/broker/summary` returns real OANDA data ($99,986.57 NAV).
- Frontend: dashboard renders cleanly, Total Wealth animates, all legacy panels still operational.
- Lint: clean (Python ruff + JS ESLint).

## Profit-Lock Dashboard Webhook (2026-05-08, **NEW**)

Wires `jarvis-synth` (Railway) → `dashboard` (Emergent) so the live "Locked Profits" widget reflects every +5% profit-sweep in real time.

### Backend (dashboard)
- `POST /api/broker/profit-locks` — accepts `{timestamp, amount, nav_at_lock, baseline_before, baseline_after, source}`. Auth via `X-Lock-Token` header matching env `BROKER_LOCK_TOKEN`. Idempotent: dedupes on `timestamp` (re-posts return `{stored:false, duplicate:true}`). Closed (503) when token env unset — fail-secure.
- `GET /api/broker/profit-locks` — recent events, newest first, for the dashboard.
- `GET /api/broker/summary` already sums these into `locked_profits` + `total_wealth`.

### jarvis-synth
- New `app/dashboard_webhook.py` — async best-effort POST via `httpx`. Errors swallowed, never breaks the trading loop.
- `app/main.py` `profit_lock_heartbeat` calls it after every successful lock.
- `app/config.py` adds optional `DASHBOARD_LOCK_WEBHOOK_URL` + `DASHBOARD_LOCK_TOKEN` env vars (skip silently if unset).
- 5/5 webhook tests pass; total jarvis-synth tests: **27/27 green**.

### Verified end-to-end
- Auth rejection (no/wrong token) → 401 ✓
- Valid post → `stored:true` ✓
- Duplicate timestamp → `duplicate:true` ✓
- `/broker/summary` reflects `locked_profits=$823.95`, `total_wealth=$100,810.52`, `locked_events=2` after 2 fake POSTs ✓

### User action required for production
1. On Railway → `jarvis-synth` service → Variables → add:
   - `DASHBOARD_LOCK_WEBHOOK_URL=https://jarvis-agent-16.preview.emergentagent.com/api/broker/profit-locks`
   - `DASHBOARD_LOCK_TOKEN=<value of BROKER_LOCK_TOKEN from /app/backend/.env>`
2. Redeploy. Next time NAV crosses +5%, the dashboard's "Locked Profits" cell updates automatically.

## Multi-Broker Dashboard + Alpaca Worker (2026-05-08, **NEW**)

Dashboard now displays **OANDA forex** and **Alpaca stocks+crypto** side-by-side as separate sections, with a unified Combined Wealth supercard above them.

### New Railway worker: `/app/jarvis-synth-alpaca/`
- Mirror of `jarvis-synth` with OANDA modules swapped for Alpaca:
  - `alpaca_fetch.py` — historical bars (crypto + stocks via IEX feed for free tier)
  - `alpaca_exec.py` — paper-trading executor with bracket SL/TP (stocks) and market orders (crypto)
- Reuses **all** of Tauric debate, Kronos forecaster, Synth, Risk Guard, Profit-Lock, Daily Summary unchanged.
- Schedule: `*/30 * * * *` (every 30 min, 24/7) — crypto trades any hour, stock orders rejected outside US RTH (harmless logged rejections).
- Default instruments: **5 crypto + 5 stocks** — `BTC/USD,ETH/USD,SOL/USD,AVAX/USD,LTC/USD,NVDA,TSLA,AAPL,AMD,META`.
- **Profit-lock events tagged `source: "jarvis-synth-alpaca"`** so dashboard attributes locks correctly.
- 27/27 pytest passing, lint clean.
- Live smoke test: account ACTIVE ($100k cash, $200k buying power), crypto bars + stock IEX bars both streaming.

### Dashboard backend additions (`/app/backend/server.py`)
- `GET /api/broker/oanda/summary` — OANDA forex (alias of original `/broker/summary`).
- `GET /api/broker/alpaca/summary` — Alpaca multi-asset, includes `positions_detail[]`.
- `GET /api/broker/all` — combined view, both brokers + summed `combined.total_wealth`.
- `nav_snapshots` collection now keyed by `(broker, date)` — DoD per broker.
- `profit_locks` events filtered by `source` tag for proper attribution.
- New `alpaca_client.py` module (read-only account + positions reader).

### Dashboard frontend additions
- `MultiBrokerHero` component: slim Combined Wealth supercard + two stacked broker cards (OANDA violet accent, Alpaca cyan accent), each with full NAV/Locked/Positions/Margin breakdown, DoD pills, live indicators, framer-motion entrance.
- Refreshes every 15s. One fetch to `/broker/all` powers all three sections.

### Verified live
- OANDA: $99,991 NAV + $823.95 locked = $100,815 wealth ✓
- Alpaca: $100,000 NAV (real paper account) ✓
- Combined: **$200,815.20** total wealth ✓

### User actions to make Alpaca live on Railway
1. New Railway service → `Root Directory: jarvis-synth-alpaca`
2. Copy all env vars from `.env.example`, fill in:
   - `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (from https://app.alpaca.markets/paper)
   - `TELEGRAM_BOT_TOKEN` (use a **different bot** than jarvis-synth to avoid 409 conflicts)
   - `DASHBOARD_LOCK_WEBHOOK_URL` + `DASHBOARD_LOCK_TOKEN` (same as jarvis-synth)
3. Mount Volume at `/app/data` for ledger persistence.

## Last session ops checklist

- [x] Tavily key validated against live API
- [x] New Telegram bot `@Jervistradebot` (token `8694341880:...`) working
- [x] forex-agent boot smoke test passed end-to-end
- [x] kronos-agent scaffolded, lint clean
- [x] knowledge-arb scaffolded, lint clean, **live end-to-end smoke test passed**
- [ ] forex-agent Railway deploy green (blocked on user re-pasting token)
- [ ] kronos-agent Railway deploy
- [ ] knowledge-arb Railway deploy

## jarvis-synth (5-layer autonomous trader, on Railway)

5-layer pipeline: News+Macro → Tauric 7-agent debate → Kronos ML → JARVIS Synth → Risk Guard + OANDA exec. Paper-only on OANDA practice. Uses second bot to avoid 409 conflicts with `forex-agent` polling.

### Profit-Lock (2026-05-07)
- Polls OANDA NAV every `PROFIT_LOCK_CHECK_INTERVAL_SECONDS`. When NAV ≥ baseline × (1+threshold%), locks the gain into `data/ledger.json`, resets baseline to new high-water mark, sends Telegram alert. Daily-loss-limit baseline is reset alongside so locks don't trigger flat-day halts.
- Default threshold 5% per sweep. Tested in `tests/test_profit_lock.py` (8/8 passing).

### Daily Summary Report (2026-05-08, **NEW**)
- `app/daily_report.py` — persistent daily snapshot tracker at `data/daily_history.json`. Inception balance fixed at first boot.
- Snapshot fields: `nav_open`, `nav_close`, `realized_today`, `open_positions`, `total_locked`, `total_wealth`.
- Telegram message renders 3 sections: **TODAY** (P&L + NAV delta), **THIS WEEK** (rolling 7-day), **ALL-TIME** (inception → today, days active, locked profits, total wealth, total return %, avg daily).
- **Scheduled:** `55 23 * * *` UTC (daily, 5 min before midnight rollover) via APScheduler.
- 6/6 tests passing in `tests/test_daily_report.py`. Total jarvis-synth tests: **22/22 green**, lint clean.

## Backlog (refreshed 2026-05-08)

- **P0 user action:** Save to GitHub → Railway redeploys jarvis-synth with the daily-summary feature.
- **P1:** Binance public API for 24/7 crypto paper-testing (OANDA practice has no crypto instruments).
- **P1:** Watch Moonshot Kimi balance — fallback chat/signal in dashboard returns 429 when low.
- **P2:** Scale jarvis-synth from 5 → 10 instruments after win-rate validation.
- **P2:** MT4/MT5 Windows VPS + Cloudflare tunnel (deferred).
- **P2:** Per-service bots if signal channels get noisy.
- **P2:** Shared MongoDB so kill-switch / cooldown / daily-halt state survives Railway redeploys.
- **P2:** Kronos upgrade to `Kronos-base` on GPU host.
- **P2:** knowledge-arb v2 — add Reddit + Google Trends.
