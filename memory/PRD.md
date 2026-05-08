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
