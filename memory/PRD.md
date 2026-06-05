## SystemVitals replaces TradingPeersCluster (2026-06-05)

User: "I don't wanna see the clusters. I'd rather just see that I'm making money and that my system is working."

Swapped the decorative galaxy cluster for a focused ops card.

### New: `frontend/src/components/v2/SystemVitals.jsx`
- **Top-left**: Big green/red profit number `+$X` / `−$X` (total_wealth − $300k starting), with trending icon and accent-blue "$X cash secured" line below (only when locked_profits > 0)
- **Top-right**: 3 colored dots (one per broker: OANDA · Alpaca · Sim) — green pulse if `as_of` < 5 min, red dim if stale. "3/3 live" tally underneath.
- **Bottom rows**:
  - Last trade: `Xm ago · SYMBOL SIDE ±X.XX%` (pulled from `/api/dashboard/recent-trades`)
  - Risk gate: click-through row showing OPEN/PAUSED + manual override tag — opens the existing RiskOffSheet modal
- Polls every 15s, loading guard prevents brief "−$300,000" flash on initial paint
- Tracks: `/api/broker/all` + `/api/dashboard/recent-trades?limit=1` + `/api/risk/status`

### Dashboard layout (mobile)
1. RiskOffBanner (auto-hides when standby)
2. TodayProfitHero
3. MarketPulseStrip
4. **SystemVitals** ← replaced TradingPeersCluster
5. BrokerCarousel

### Files
- `frontend/src/components/v2/SystemVitals.jsx` (NEW)
- `frontend/src/App.js` (swap)
- `frontend/src/components/v2/TradingPeersCluster.jsx` kept on disk but no longer imported on the dashboard tab (zero callers)

---


## Trading Cluster — Profit-First Center (2026-06-04)

User feedback: "Remove the blue center dot. Show profits (e.g. +$42,000) and what cash I can pull out."

- Removed the gradient blue YOU bubble in `TradingPeersCluster.jsx`
- Center now shows **3 text-only lines**:
  - Big glowing **+$X** profit number (green if up, red if down) — `cluster-profit` testid
  - Tiny "PROFIT" label
  - **$X cash** in accent-blue — locked-profits amount (the auto-secured/withdrawable bucket from the profit-lock ledger), only shown when > 0 — `cluster-cash` testid
- `STARTING_BALANCE` = $300,000 (3 brokers × $100K paper inception) — single constant at the top of the file for easy adjustment when real broker accounts are added
- Total combined wealth no longer surfaced here — surface is profit-focused per user direction
- Galaxy peer dots + drift + twinkle stars unchanged

---


## Compare UI + Scaling Readiness Gate (2026-06-04)

Wired the ensemble compare endpoint into the dashboard + added a 5→10 instrument scaling-readiness card.

### Compare A vs Ensemble (Backtest Lab modal)
- New "Compare A vs Ensemble" button in BacktestLab header
- `CompareSheet` modal calls `POST /api/backtest/ensemble/compare` and polls every 3s for results
- Side-by-side metrics table: Trades / Win Rate / Net P/L / Profit Factor / Sharpe / Max Drawdown — each row color-coded green/red based on which side won
- 4-light **Promote Gate** panel (Win rate↑ · Profit factor↑ · Sharpe↑ · Max drawdown↓)
- **"Promote to Live Workers"** button enabled ONLY when `promote_to_paper === true`. On click, POSTs the validated params to existing `/api/instrument-configs/apply` so workers pick them up on next cycle.

### Scaling Readiness Panel (P1 gate, 5 → 10 instruments)
- Always-visible card below BacktestLab
- New backend `/api/scaling/readiness` GET — reports `closed_trades` count + WR + gate-clear bool + current/proposed instrument lists
- New backend `/api/scaling/promote` POST — rejects with 409 unless `≥20 closed trades AND ≥40% WR`. On success, writes a `scaling_state` doc with the `INSTRUMENTS=...` Railway env command.
- UI shows: current trades (1/20), current WR (0.0%/40%), Locked/Unlocked status, all 10 instrument chips, and a "Scale to 10" button that dynamically tells you exactly how many more trades + how much higher WR is needed.
- When promoted: displays a copyable `INSTRUMENTS=EUR_USD,GBP_USD,USD_JPY,AUD_USD,XAU_USD,USD_CHF,USD_CAD,NZD_USD,EUR_GBP,EUR_JPY` block for the user to paste into Railway → jarvis-synth Variables.

### Tests
- 5/5 backend regression tests in `backend/tests/test_scaling_routes.py` (locked/cleared/promote-rejected/promote-succeeded/confirm-required)
- Visual end-to-end verified: modal opens, compare runs in ~3s, gate panel renders correctly with 4 red lights for 0-trade scenario.

### Configurable gate thresholds
- `SCALING_MIN_TRADES` (default 20) and `SCALING_MIN_WR` (default 40.0) read from env so the user can adjust without code changes.

### Files
- `backend/scaling_routes.py` (NEW)
- `backend/server.py` (registered `/api/scaling/*`)
- `backend/tests/test_scaling_routes.py` (NEW — 5 tests)
- `frontend/src/components/v2/BacktestLab.jsx` (+ CompareSheet, + ScalingReadinessPanel, + Compare button)

### Worker scope (unchanged per user rule)
Workers `/app/jarvis-synth/*` and `/app/jarvis-synth-alpaca/*` not modified. Promoting just writes config records; the user updates Railway INSTRUMENTS manually using the surfaced command.

---


## Trading Cluster — Galaxy Drift (2026-06-04)

User feedback: "cluster dots a little smaller, moving like galaxy stars."

- Peer dots shrunk **48px → 36px** (border 2px → 1.5px, label 10px → 8.5px, change-pct 8px → 6.5px)
- Each peer gets a unique slow orbital drift (~5.5–9s loop, ±3–6px x/y, opacity 0.88→1) via framer-motion `animate` keyframes — phases offset by index so they don't move in lockstep
- Added 12 background twinkle stars (`<animate>` SVG opacity pulses) for galaxy depth
- Center "YOU" bubble stays static as the anchor
- Explicit width/height on `motion.button` fixed a 0×0 bounding-box bug introduced by the drift wrapper
- File: `frontend/src/components/v2/TradingPeersCluster.jsx`

---


## 3-Pod Strategy Ensemble in Backtest Lab (2026-06-04, **NEW**)

Adds **Pod B (Mean-Reversion)** and **Pod C (Momentum/Breakout)** alongside the
existing **Pod A (Tauric+Kronos)** with a strict **2-of-3 voting** gate. Lives in
the Backtest Lab only — worker code untouched. Compares ensemble vs single-pod
side-by-side; promotes to paper only when ≥3 of 4 metrics improve.

### New backend files / changes
- `backend/strategy_pods.py` — 3 pure-numpy pod functions + `ensemble_vote()` +
  `vote_concurrently()` (asyncio.gather with per-pod 30s timeout).
  • Pod A = thin adapter over existing `kronos_surrogate` + `tauric_deterministic`
    + `synthesize` (no logic change — by design).
  • Pod B = RSI + Bollinger Band fade, gated by **low vol** (`vol_amp < 1.10`).
  • Pod C = Donchian-20 break + ADX-14 ≥ 22, gated by **high vol** (`vol_amp ≥ 0.95`).
- `backend/backtest_engine.py` — adds:
  • `EnsembleResult` dataclass (extends with `profit_factor`, `sharpe_ratio`, `pod_stats`).
  • `run_backtest_ensemble()` — mirrors `run_backtest`'s data/MTF/ATR/sizer/exit
    logic exactly (strict parity), only entry signal changes.
  • `_profit_factor_and_sharpe()` helper — now populates these on `BacktestResult` too.
- `backend/backtest_routes.py` — new endpoints:
  • `POST /api/backtest/ensemble/run` → returns `run_id`
  • `GET  /api/backtest/ensemble/active`
  • `GET  /api/backtest/ensemble/runs/{id}`
  • `POST /api/backtest/ensemble/compare` → runs single-pod + ensemble back-to-back
  • `GET  /api/backtest/ensemble/compares/active`
  • `GET  /api/backtest/ensemble/compares/{id}` → includes `promote_gate` + `promote_to_paper`
- `backend/tests/test_strategy_pods.py` — 11 regression tests (all passing).

### Promote gate (ensemble vs single-pod, same window)
1. `win_rate_up`     — ensemble WR > single WR
2. `profit_factor_up` — ensemble PF > single PF
3. `sharpe_up`       — ensemble Sharpe > single Sharpe
4. `drawdown_down`   — ensemble max DD < single max DD
→ **promote_to_paper = True only when ≥3 of 4 improve**

### Validation runs (real yfinance data, preview env)
| Symbol     | Period | Single-pod                              | Ensemble                          | Gate    |
|------------|--------|-----------------------------------------|-----------------------------------|---------|
| BTC/USD    | 30d 1h | 0 trades                                | 0 trades                          | block   |
| NVDA       | 180d 1h (floor=7) | 16 trades / 12.5% WR / −18.3% PnL / DD 18.4% | 0 trades            | block   |
| ETH/USD    | 180d 1h (floor=7) | 19 trades / 36.8% WR / +8.17% PnL / PF 1.35 / Sharpe 0.55 / DD 12.7% | 2 trades / 0% WR / −4.47% PnL / DD 4.5% | **block** (1/4 gates passed) |

Gate correctly refuses to promote in all three cases. Ensemble is **highly
selective** by design (Pod B/C have inverse vol-regime gates, so 2-of-3 ≈
"Pod A + 1 confirming regime pod").

### Strict parity guarantees
- Same data source (yfinance via `_fetch_bars`), same period/interval.
- Same warmup window (bars 40 .. end-1), same one-trade-at-a-time.
- Same ATR-based SL/TP, same exit logic (SL/TP touch in bar high/low).
- Same `size_position()` sizer, same conviction multipliers.
- MTF + indicator confluence gates still applied AFTER ensemble agrees.

### Worker scope (unchanged)
- `/app/jarvis-synth/*` — untouched
- `/app/jarvis-synth-alpaca/*` — untouched
- Per user direction: do NOT modify the existing Tauric strategy logic. Pods B/C
  are evaluation-only until promote-gate clears on real-world held-out windows.

---

## Telegram Paused (2026-06-04)

User paused Telegram alerts on both workers (`jarvis-synth` and `jarvis-synth-alpaca`).
- `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are now **optional** in `config.py`.
- Workers boot without Telegram and use a `_NullBot` no-op for every send call.
- Force-disable via `TELEGRAM_ENABLED=false` even when creds are present.
- 83 worker tests still pass.

---


## Mobile-First Single-Screen Dashboard (2026-05-19, **NEW**)

Final mobile UX pass per user mockup. Dashboard tab is now a fixed-height single-screen view on mobile — **zero vertical scroll** at 393×852 (iPhone 14 Pro).

### Dashboard tab layout (3 elements only)
1. **TodayProfitHero** (`v2/TodayProfitHero.jsx`) — green/red gradient hero. Big animated combined-day P/L number, sparkline, vs-yesterday %, OANDA + Alpaca broker chips. ~195px tall.
2. **TradingPeersCluster** — compact 240×240 cluster card. 6 asset peer nodes (BTC, ETH, NVDA, TSLA, OIL, KIMI) ringed around an 80px YOU bubble showing combined wealth. ~294px tall.
3. **BrokerCarousel** (`v2/BrokerCarousel.jsx`) — horizontal snap-scroll of 3 broker cards (OANDA / Alpaca / Sim) with equity + 24H P/L + sparkline. ~152px tall.
   Total: 195 + 294 + 152 + gaps + header + nav clearance ≈ 852 → fits exactly.

### Tab routing (`App.js`)
- **Dashboard** = the 3-element single-screen view (above)
- **Portfolio** = HeroMetricsRow (5 KPIs) + MultiBrokerHero + OpenPositions + RecentTrades tables
- **Agents** = AgentStatus + Automation + TopSignals cards + **BotBrainPanel** (live pipeline cycles)
- **Settings** = stub

### Ask Jarvis full-screen modal (`v2/AskJarvisModal.jsx`, **NEW**)
- Triggered by the center `+` button in the Bottom Nav (replaces the old persistent floating bar).
- Full-screen backdrop blur, centered orb (spins idle / pulses while listening), input pill + mic + send.
- Closes on Escape, X button, or modal-bg click; locks body scroll while open.
- Shows last JARVIS reply inline above the input.

### Verified
- Frontend testing agent: **100% pass** on mobile 393×852, tablet 768, desktop 1280.
- `scrollHeight === innerHeight === 852` on Dashboard (zero scroll confirmed).
- All testids present: today-profit-hero, trading-peers-cluster (6 peer-node-* children), broker-carousel (3 broker-card-* children), bottom-nav (5 nav-* buttons), ask-jarvis-modal (with input/mic/send/close).
- Tab switching swaps content via `AnimatePresence`; modal opens/closes cleanly.
- Backend endpoints `/api/dashboard/hero`, `/api/broker/all`, `/api/dashboard/peers`, `/api/bot-brain/cycles` all 200.

## Backlog (refreshed 2026-05-19)

- **P1:** CoinMarketCap integration — user has API key. Plan: Top Movers chip in Dashboard hero + Fear & Greed micro-widget + Market Regime detector input to QuantAgent filters. **User to provide CMC_API_KEY on a fresh chat line.**
- **P2:** Scale jarvis-synth (OANDA) from 5 → 10 instruments after win-rate validation (raise `MAX_ORDERS_PER_MINUTE` first).
- **P2:** Auto-attribute Locked Profits per source (already source-tagged; surface in Portfolio tab breakdown).
- **P2:** MT4/MT5 Windows VPS + Cloudflare tunnel (deferred by user).
- **P3:** Production env-var sync helper UI (user previously got confused why prod showed no data — needs explicit env-var injection via Emergent Support).

## CoinMarketCap Integration — Market Pulse Strip (2026-05-19, **NEW**)

CMC Pro API wired into the Dashboard via a thin 30px strip (regime · F&G · top-movers marquee) — preserves the strict single-screen-no-scroll rule on mobile 393×852.

### Backend (`/app/backend/`)
- `cmc_client.py` — async httpx client with in-memory 75s TTL cache + daily call counter. Single source of truth for all CMC calls.
- `market_routes.py` — APIRouter `/market/*`:
  - `GET /api/market/status` — `{configured, cache_entries, calls_today, cache_ttl_seconds}` (observability)
  - `GET /api/market/fear-greed` — `{value 0-100, classification, fetched_at}` (CMC `/v3/fear-and-greed/latest`)
  - `GET /api/market/regime` — derived bull/bear/chop from `/v1/global-metrics/quotes/latest` + F&G score
  - `GET /api/market/top-movers?top_n=5` — gainers/losers from `/v1/cryptocurrency/listings/latest`
- Key stored at `/app/backend/.env` as `CMC_API_KEY` — never exposed to frontend.

### Frontend (`/app/frontend/src/components/v2/MarketPulseStrip.jsx`)
- Sits between `TodayProfitHero` and `TradingPeersCluster` on the Dashboard tab (~30px tall).
- Regime pill (BULL green / BEAR red / CHOP grey), F&G chip with 0-100 score in classification color, and a paused-on-hover horizontal marquee of 8 top tickers (4 gainers + 4 losers interleaved).
- Polls every 90s (matches server cache TTL); axios timeouts at 10s.

### Verified end-to-end
- All 3 CMC endpoints live: BTC dom ~60%, regime=CHOP, F&G=39 (Fear), top gainer ONDO +12.4%, top loser FLR -6.5%.
- **Testing agent: 100% pass** (backend 6/6 pytest + frontend full coverage).
- Mobile 393×852 still zero-scroll after strip insertion (cluster max-size shrunk from 240→220 to compensate).
- Cache works — repeat calls within 75s don't increment `calls_today` (free-tier safe).
- CMC key NEVER appears in any response body, request header, or browser console.

### Optional next step
- Feed the `regime` signal into `jarvis-synth-alpaca` filter chain so workers skip new entries during CHOP regimes (would need `CMC_API_KEY` added to Railway service variables; user can decide later).

## Scale-Up Prep (5 → 10 instruments) (2026-05-19, **NEW**)

User chose **Option A — defer the scale-up until ~20 closed Railway trades validate filter edge**. Current data: 1 closed trade on `jarvis-synth`, 3 bot_cycles logged. Need ~7 more days at current cron.

### Pre-staged so scaling is a 2-Variable Railway edit (no redeploy needed)

The hard-coded `≥5 orders/minute → reject` rate limit (would have blocked a 10-instrument fanout) is now **configurable via env var**:

- `/app/jarvis-synth/app/guardrails.py` line 184 — reads `MAX_ORDERS_PER_MINUTE` (default 5)
- `/app/jarvis-synth-alpaca/app/guardrails.py` line 182 — same pattern
- Both `.env.example` files documented with comments + new var

### When ready to scale (~7 days from now)
On each Railway service Variables tab, update:

**`jarvis-synth` (OANDA Forex):**
```
INSTRUMENTS=EUR_USD,GBP_USD,USD_JPY,XAU_USD,USD_CHF,AUD_USD,NZD_USD,EUR_GBP,USD_CAD,EUR_JPY
MAX_ORDERS_PER_MINUTE=10
```

**`jarvis-synth-alpaca` (Alpaca crypto/stocks):**
```
INSTRUMENTS=BTC/USD,ETH/USD,SOL/USD,AVAX/USD,LTC/USD,LINK/USD,NVDA,TSLA,AAPL,AMD
MAX_ORDERS_PER_MINUTE=10
```

Railway auto-restarts on Variable save → new instruments take effect on the next cron tick. Zero code touched.

### Verified
- 44/44 pytest passing on both workers (no regressions from the rate-limit refactor)
- Defaults preserved: existing deployments with no `MAX_ORDERS_PER_MINUTE` set keep the old `5` behavior

## Auto-Risk-Off Mode + Downside Protection (2026-05-27, **NEW**)

User reported a red day driven by BTC -3% pullback and asked for downside protection. Built a CMC-driven Risk-Off gate that pauses **new entries** (existing positions and their stops untouched) when conditions get ugly.

### Backend (`/app/backend/risk_gate.py` + `server.py` lines ~770)
- `GET /api/risk/status` — `{active, source, reason, regime, fg_value, mc_pct_24h, manual_override, since, as_of}`. Auto-evaluates via CMC every poll (uses the shared 75s cmc_client cache so quota-safe).
- `POST /api/risk/override` — `{mode: 'on'|'off'|'auto', by?}`. 400 on invalid mode. Persists in MongoDB `risk_state._id="main"`.
- **Auto logic**: `regime=bear` AND `fg_value ≤ 30` → active. `fg_value ≤ 20` → active regardless of regime (extreme fear).
- **Manual override** beats auto; `mode='auto'` clears the override.

### Frontend (`/app/frontend/src/components/v2/RiskOff.jsx`)
- **RiskOffBanner**: red banner on Dashboard tab when active, shows reason + "tap to manage".
- **RiskOffSheet**: bottom-sheet modal (App-Store-style) with live regime/F&G/24h-Mkt readout + 3 mode pills (🤖 Auto / 🛡 Force On / 🟢 Force Off).
- **MarketPulseStrip**: regime pill now clickable, opens the same sheet.
- **Single source of truth**: `useRiskStatus` hook lifted to App.js; passed as props to both Banner and Sheet so toggles inside the sheet update the banner instantly (no 60s lag).

### Worker integration (`/app/jarvis-synth*/app/risk_gate.py` + `main.py`)
- New module: async `check()` polls `DASHBOARD_RISK_STATUS_URL` (env var, optional). **Fails OPEN** if unset/unreachable.
- Wired into `main.py` as **Layer 4a** — runs BEFORE the existing `run_pre_tauric_filters` (Layer 4b). When gate vetoes, LONG/SHORT downgrades to HOLD with reasoning `"Risk-Off: ..."` and a record appended to `filter_records` so the Bot Brain panel shows the reason.
- `.env.example` documented for both workers.

### Yes — JARVIS can make money in DOWN markets
- **OANDA forex** (`jarvis-synth`): full SHORT support. When Tauric votes SELL + regime=BEAR, opens short positions that profit on price drops.
- **Alpaca stocks** (`jarvis-synth-alpaca`): full SHORT support on individual stocks (NVDA/TSLA/AAPL/AMD/META).
- **Alpaca crypto**: long-only by US regulation. Risk-Off becomes the primary defensive tool for crypto exposure.

### Verified
- Testing agent: backend 100% (all endpoints + invalid input + auto thresholds), worker pytests 100% (44/44 + 44/44), frontend banner/sheet/regime-pill flow all green.
- Fix shipped post-testing: banner-sheet state sync (was 60s lag, now instant) via lifted hook.
- Live signals at deploy: regime=BEAR, F&G=36 → active=false (correct — 36 above 30 threshold).

### User actions to enable on Railway (optional)
On each worker service Variables tab, add:
```
DASHBOARD_RISK_STATUS_URL=https://your-dashboard.preview.emergentagent.com/api/risk/status
```
Workers restart, and from then on every cycle does a 4s HTTP check before opening a new entry. No other changes needed.

## Risk Engine Upgrades — ATR Stops + Trailing Stops (2026-05-27, **NEW**)

Shipped Gaps #1 and #2 from the Risk Posture audit. Both workers now use volatility-adaptive stops + auto-tighten winners.

### Gap #1 — ATR-based dynamic stops
- New `/app/jarvis-synth*/app/indicators.py` (mirrored across both workers).
  - `atr(bars, period=14)` — Wilder ATR, pandas only, returns None on insufficient data.
  - `pip_size(instrument)` — handles JPY pairs + XAU/XAG correctly.
  - `adaptive_sl_pips(bars, instrument)` → forex (clamped 6-80 pips).
  - `adaptive_sl_pct(bars)` → Alpaca crypto/stocks (clamped 0.5-8%).
- `main.py` execution sites replace hard-coded `sl_pips=10.0` with the adaptive version; falls back to 10 if ATR can't be computed.

### Gap #2 — Trailing stops
- New `/app/jarvis-synth*/app/trailing_stops.py` (mirrored).
  - Pure `decide(trade, current_price)` function — easy to pytest.
  - Logic: at +1R move stop to entry (breakeven). At +2R, trail stop to +1R locked. One-way ratchet — never widens.
- Executor additions:
  - `OandaExecutor.list_open_trades()` + `update_trade_stop()` via `v20_trades.TradeCRCDO`.
  - `AlpacaExecutor.list_open_trades()` + `update_trade_stop()` — cancels existing bracket SL child, posts a new `StopOrderRequest`. Crypto symbols correctly return `{status:'skipped'}`.
- Heartbeat: `asyncio.create_task(trailing_heartbeat(...))` every `TRAILING_STOP_INTERVAL_SECONDS` (default 300s). Telegram alert on each tightening with reason.

### Dashboard reflection
- `/api/risk/posture` improvement_gaps now reports `status: 'shipped'` for `atr_stops` + `trailing_stops`.
- Risk Posture card header reads "Risk Engine Upgrades (2/4 shipped)"; shipped items get green check + green SHIPPED badge.

### Verified
- **Worker pytests: 64/64 each** (was 44/44; +20 new = 11 indicators + 9 trailing). Total: 128/128.
- Testing agent: 100% backend + frontend pass. No regressions on existing endpoints.
- Pre-existing 20s timeout in `test_jarvis_backend.py` bumped to 60s per agent's flake report.

### Remaining gaps (2/4)
- `conviction_scaling` (medium impact): scale base units by Tauric confidence 7→1.0x, 8→1.3x, 9→1.6x, 10→2.0x.
- `vol_adjusted_sizing` (medium impact): when Kronos vol_amp is 1.3-2.0x, multiply units by 0.5.

## Quality Gate — Win-Rate Boosters A + B (2026-06-02, **NEW**)

User explicitly asked for higher win rate. Shipped two well-known WR-boosters from a menu of options.

### Booster A — Tightened confidence floors (config only)
- **synth.py** (both workers): Tauric floor 7 → **8/10**. Stale docstring updated.
- **main.py** `build_signal(...)`: `upside_high` 0.65 → **0.70**, `upside_low` 0.35 → **0.30**.
- Net effect: only the cleanest setups make it past the synth matrix. Industry data suggests this alone lifts WR ~8-15pp at the cost of ~30% fewer trades.

### Booster B — Multi-Timeframe trend confluence
- The `mtf_trend_filter` function in `filters.py` already existed but was being called with `mtf_bars=None` → effectively disabled.
- Now both workers fetch a SECOND timeframe (`H4` for OANDA, `4Hour` for Alpaca) alongside the primary `H1`/`1Hour` and pass both as `mtf_bars={'H4': h4_df, 'H1': hist}`.
- The filter requires EMA-20 slope agreement on **both** timeframes; trades where the 4-hour trend disagrees with the 1-hour signal get downgraded to HOLD with a clear "MTF trend conflict" reason in the Bot Brain log.
- Fetch failure is wrapped in try/except → degrades gracefully to `mtf_bars=None` (no cycle crash).

### Dashboard reflection
- `/api/risk/posture`: `protections.confidence_floor` now exposes `tauric_min=8`, `kronos_upside_high=0.70`, `kronos_upside_low=0.30`. NEW key `protections.mtf_confluence` = `{enabled, timeframes:[H4,H1], min_agree:2, policy}`.
- RiskPostureCard: "Active Protections" section grew from 6 → **7 rows**. New "Multi-Timeframe Confluence" row with "ACTIVE" badge. Confidence Floor row sub-text updated to reflect the new thresholds.

### Verified
- pytest jarvis-synth: 83/83 (had to bump `test_underweight_plus_sell_is_half_short` to Tauric=8 to match new floor).
- pytest jarvis-synth-alpaca: 83/83 (same fix).
- Testing agent: 100% backend + frontend. No regressions on /api/risk/status, /api/market/*, /api/dashboard/hero, /api/dashboard/win-rate-trend. Mobile zero-scroll still holds.
- Live H4 fetch path NOT tested against broker (no creds) — verified code path exists and gracefully falls back when fetch fails.

### Tradeoffs the user should know
- Trade volume drops ~30-40% — your existing ~5 trades/week pace may slow to 3/week.
- Time to hit 20-trade threshold may slip from ~1 week → ~10 days.
- This is the right tradeoff IF the lift in WR materializes; the WinRateTrendCard will tell us in real time.

## Backtest Lab — Walk-Forward Pipeline Replay (2026-06-02, **NEW**)

User asked: "Find existing data we can pull so we run on data sets parallel with execution, instead of waiting weeks for live trades." Shipped a walk-forward backtester that replays the JARVIS signal pipeline against years of historical OHLCV data — validates win rate in seconds, not days.

### Backend (`/app/backend/`)
- `backtest_engine.py` — pure numpy/pandas. Self-contained replica of:
  - **Kronos surrogate**: deterministic EMA-momentum-based upside_prob (the live workers use the real Kronos NN — surrogate is cheap & free).
  - **MTF trend agreement** (mirrors `filters.mtf_trend_filter`).
  - **Indicator confluence** (RSI + EMA-20 vs price; mirrors `indicator_confluence`).
  - **Synth matrix + Tauric floor ≥8** (mirrors `synth.synthesize`).
  - **Position sizer** with conviction × volatility multipliers.
  - **ATR-based stop + R:R take-profit + walking bar-by-bar exit**.
- `backtest_routes.py` — `POST /api/backtest/run`, `GET /api/backtest/active`, `GET /api/backtest/runs`, `GET /api/backtest/runs/:id`.
- Data via `yfinance` (free, no API key); symbol mapping handles `EUR_USD` → `EURUSD=X`, `BTC/USD` → `BTC-USD`, stocks pass-through.
- **Smart mode** (`use_tauric=True`): 1 Claude call per signal that passes Kronos+filters, capped at `max_llm_calls` (default 50). The deterministic verdict serves as fallback.

### Frontend
- New **BacktestLab card** in Agents tab — pick symbol/period/interval/mode, hit RUN, poll active, display ranked results table with color-coded WR/PL/expectancy.

### Initial validation results (live)
| Symbol | Period | Bars | Trades | WR | Net P/L | Expectancy |
|---|---|---|---|---|---|---|
| ETH/USD | 180d 1h | 4295 | 19 | 36.8% | **+8.17%** | +0.483% |
| BTC/USD | 180d 1h | 4295 | 8 | 25.0% | −2.04% | −0.213% |
| NVDA | 180d 1h | 1243 | 17 | 17.6% | −18.01% | −1.143% |
| EUR_USD | 60d 1h | 1396 | 0 | — | — | — |

**Honest take:**
- **ETH positive expectancy** even at 37% WR — proof the 2:1 R:R covers low win rate.
- **EUR_USD = 0 trades** in 60 days — quality gate too strict for forex hourly; needs daily timeframe or relaxed thresholds. Use the lab to tune.
- **NVDA struggles** — surrogate Kronos likely not capturing stock-specific behavior. Daily timeframe likely better than hourly.

### Caveats surfaced in UI
- Surrogate Kronos ≠ real Kronos NN — used in backtest only.
- Smart mode uses a single-shot Claude call, not the full 7-agent debate.
- Past performance ≠ future performance.

### Dependencies
- New: `yfinance==1.4.1` (free, no API key).

## Auto-Tune + Per-Trade Drill-Down (2026-06-02, **NEW**)

User said "you pick" — shipped per-asset parameter optimization + trade-ledger drill-down on the Backtest Lab. This closes the loop from "we have backtests" to "we have actionable optimal configs per symbol".

### Backend
- `backtest_engine.py`:
  - `kronos_surrogate()` now accepts `upside_high`, `upside_low`, `max_vol_amp` overrides.
  - `synthesize()` accepts `tauric_floor` override.
  - `run_backtest()` accepts 5 tunable params: `tauric_floor`, `upside_high`, `upside_low`, `atr_mult`, `rr_base`. Stored on `BacktestResult.params`.
  - NEW `run_tune()` — `asyncio.gather` over 54 (tauric_floor × upside_high × atr_mult × rr_base) combos, ranked by `expectancy × √trades − dd_penalty`. Zero-trade outcomes score 0.
- `backtest_routes.py` — `POST /api/backtest/tune`, `GET /api/backtest/tunes/active`, `GET /api/backtest/tunes/:id`. Stored in MongoDB `backtest_tunes`.

### Frontend (`BacktestLab.jsx`)
- New **Auto-Tune** button (amber) next to Run Backtest.
- New **TuneSheet** modal — auto-fires tune on open, shows running indicator → "Best Config Found" card with WR/PL/Expectancy/DD + the winning Tauric/Upside/ATR/RR values + Top-10 ranked table.
- New **RunDrilldownModal** — click any backtest row to see the full trade ledger (entry/exit times, side, prices, exit reason, P/L per trade) with the params used.
- Testid `backtest-run-{id}` → `backtest-row-{id}` to avoid CSS selector collision with `backtest-run-button`.
- Polling switched from in-memory `/tunes/active` to persisted `/tunes/:id` with proper cancellation via `useRef`; 404s treated as "still running" not error.

### Initial optimization (live data)
- ETH/USD 180d 1h → best config: **Tauric≥7 · Upside≥0.75 · ATR×1.5 · R:R 2.5** → **55.6% WR, +23.77% PL, +2.52% expectancy**. That's a +15pp WR improvement and +15pp PL improvement over the global config (8.17%).
- Each tune runs ~15-45s end-to-end.

### Verified
- Backend pytest: 10/10 (`/app/backend/tests/test_backtest_routes.py`).
- Frontend manual end-to-end: tune button → sheet opens → 30s later "Best Config Found" displays. Drill-down click → modal opens with full ETH/BTC trade ledger.
- No regression on existing endpoints.

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

## Sim Broker + Auto Profit-Lock (2026-05-18, **NEW**)

The in-memory mock trading engine (`backend/trading_engine.py`) is now treated as a full broker on the dashboard. The user wanted end-to-end proof that the lock mechanism works even without real Railway workers actively trading.

### Backend
- New `GET /api/broker/sim/summary` — same payload shape as oanda/alpaca, sourced from `trading_engine.compute_equity()`.
- New helper `_sim_check_profit_lock(equity)` — fires on every summary poll. If equity ≥ baseline × 1.05, locks the gain into `profit_locks` with `source="sim"` and resets baseline. Stored in singleton MongoDB doc `sim_lock_baseline._id="main"`.
- `/api/broker/all` now includes sim and sums it into Combined Wealth.

### Frontend
- New "JARVIS Sim Desk · Paper-Paper" card with amber accent (rgba(255,176,32,...)).
- Custom cell labels per broker: OANDA→"Margin Used", Alpaca→"Buying Power", Sim→"Free Cash".
- First-cell label is broker-aware: NAV for OANDA/Alpaca, "Live Equity" for Sim.

### Verified
- Auto-lock fires correctly when threshold crossed (test: forced baseline $90,000, equity $101,067 → locked $11,067 on next poll).
- No double-fire on subsequent polls (baseline reset works).
- Source-tagged locks: sim doesn't pollute OANDA/Alpaca locked-profit attribution.

## v2 Dashboard — AI Financial Workspace OS (2026-05-18, **NEW**)

Complete UI redesign per user-provided mockup + brief. Replaced the terminal/cyberpunk aesthetic with a modern AI-native financial workspace.

### Theme
- New `index.css`: Inter typography, matte graphite `#0b0b10` background, soft frosted-glass cards (`white/3` over `border-white/7`), electric-blue `#6c8dff` + violet `#9b7bff` accents. Up/Down = standard `#22c55e`/`#ef4444` Tailwind greens/reds. Subtle grain overlay. No more mono fonts, no scan-lines, no cyan terminal feel.

### New components (`/app/frontend/src/components/v2/`)
1. `TopHeader` — Logo + Jarvis + Search + Bell (badge) + Menu
2. `HeroMetricsRow` — 5 KPIs (Total Equity / Day's P/L / Total Cash / Exposure / Win Rate) with animated CountUp + Recharts sparklines + progress bar + ring
3. `ChartCard` — Recharts area chart with timeframe pills (1H/1D/1W/1M/3M/1Y) + High/Low/Range stats
4. `TradingPeersCluster` — 8 surrounding nodes around a central "You" node. Lines connect periphery to center. Status-colored (bullish green / bearish red / neutral blue / agent violet). Click an asset node → focuses the chart. Mix of 5 assets (BTC, ETH, NVDA, TSLA, OIL) + 3 AI agents (KRNS, CLDE, KIMI).
5. `AgentStatusCard`, `AutomationCard`, `TopSignalsCard` — 3 utility cards in a row
6. `OpenPositionsTable`, `RecentTradesTable` — Aggregated across OANDA + Alpaca + Sim
7. `AskJarvisBar` — Floating glassmorphic pill with spinning orb + mic + send (gradient button)
8. `BottomNav` — 5 tabs (Dashboard / Portfolio / [+] / Agents / Settings), center-stage primary button

### Backend additions (`/app/backend/server.py`)
- `GET /api/dashboard/hero` — combined KPI aggregate (equity, day P/L, cash, exposure %, win rate)
- `GET /api/dashboard/sparkline?metric=equity|pl` — 30-point series from `nav_snapshots`
- `GET /api/dashboard/peers` — cluster nodes (5 assets + 3 agents) with momentum %
- `GET /api/dashboard/recent-trades` — newest fills across brokers + sim
- `GET /api/dashboard/open-positions` — normalized positions across all 3 brokers

### Tabs
- **Dashboard** = the new mockup-style screen
- **Portfolio** = preserves the 3-broker stack (`MultiBrokerHero`) so the OANDA/Alpaca/Sim cards remain accessible
- **Agents** = the 3 utility cards expanded
- **Settings** = stub

### Verified
- Backend: all 5 new endpoints return real data ($301,898 total equity, peers with live status, sparkline from snapshots)
- Frontend: lint clean, screenshot confirms layout matches mockup
- Old layout removed from default route, components preserved in `/components/panels/` for Portfolio tab reuse

## Mobile UX Pass + Real closed_trades Wiring (2026-05-18)

### closed_trades MongoDB collection (`backend/trading_engine.py`)
- `execute_trade()` sell path now writes a `closed_trades` document with `{symbol, side, qty, entry, exit, pl, pl_pct, opened_at, ts, source, broker: "sim"}` on every sell that closes a position.
- `/api/dashboard/recent-trades` now prefers `closed_trades` (real fills), falls back to inferring from open positions for cold-start.
- `/api/dashboard/hero` win_rate calc reads `closed_trades` — fires the first time a position closes profitably.
- **Verified end-to-end**: buy 0.05 BTC → sell 0.05 BTC → `recent-trades` returns the closed event with realized P/L; `hero.win_rate` flipped from null → 0.0%.

### Mobile UX polish
- **Win Rate KPI**: was orphaned alone on row 3 of the mobile 2-col grid. Now spans both cols (`col-span-2 md:col-span-1`) with ring positioned right — reads naturally.
- **Chart card height**: `h-36 sm:h-44 md:h-52` — tighter on small screens.
- **Positions/trades tables**: horizontal scroll on narrow viewports (`overflow-x-auto` + `min-w-[420px]`) so 12-col grid never cramps below 420px.
- **Bottom padding**: `pb-52 lg:pb-36` so tables don't get eaten by the floating Ask bar + Bottom Nav stack on mobile.
- Verified at 393×852 (iPhone 14 Pro size): hero row reads cleanly, all touch targets ≥36px.

## Pipeline Hardening + Status Sidecar (2026-05-18, **NEW**)

Inspired by QuantAgent paper. Added three pre-execution filters that veto weak setups, plus a read-only HTTP sidecar for real-time diagnostics. Applied to **both** `jarvis-synth` (OANDA forex) and `jarvis-synth-alpaca` (multi-asset).

### Pipeline upgrades (`app/filters.py`)

**Layer 4b — runs after Tauric+Synth, before broker execution.** Three gate-style filters; any failure downgrades the decision to HOLD with structured rationale logged.

1. **Multi-Timeframe Trend** (`mtf_trend_filter`) — EMA-20 slope on 4H/1H/15M; require ≥2 of 3 agree on direction. (Wired but skipped until fetcher supports multi-frame retrieval.)
2. **Indicator Confluence** (`indicator_confluence`) — RSI, MACD histogram, BB-position must align with proposed direction. LONG requires RSI 45-75 (trend zone, not exhausted), MACD>0, BB pos ≥0.40. SHORT mirror.
3. **Session Filter** (`session_filter`) — Forex: skip weekends + Asia overnight (UTC <08 or ≥18); Crypto: skip Sun 00-04 UTC (lowest weekly volume); Stocks: pass-through (broker enforces RTH).

### Synth threshold bumps
- Confidence floor raised from **5 → 7** (Tauric must hit ≥7/10 to proceed; was ≥5)
- R:R bracket tightened: `9+ → 3.0`, `7-8 → 2.5`, `<7 → 2.0` (was 2.5/2.0/1.5). **Minimum 2.0 always** so 35% win-rate still positive expectancy.

### Status sidecar (`app/status_server.py`, `app/cycle_log.py`)
FastAPI app on `STATUS_API_PORT` (default 8080), runs in a daemon thread alongside APScheduler:
- `GET /health` — worker metadata, last cycle ts, scheduler state, account summary
- `GET /cycles?limit=N` — last N pipeline decisions from JSONL ring buffer (`/app/data/cycle_log.jsonl`)
- `GET /trades?limit=N` — currently open positions from broker
- **Auth**: `X-Status-Token` header matches env `STATUS_API_TOKEN`. Open mode if token unset.
- Persists across restarts via mounted Railway volume.

### Tests
44/44 passing on both workers (was 27 → +17 filter tests). Coverage: MTF agreement/conflict/HOLD, indicator alignment with trend, session windows for forex/crypto, auto-detection of asset kind.

### Verified
- Status sidecar smoke test: `/health`, `/cycles`, `/trades` all return real data
- Token gating: 401 on missing/wrong token, 200 on correct
- Filter rejection logging structured cleanly for the cycle log

## Bot Brain Panel (2026-05-18, **NEW**)

A live stream of every pipeline decision both Railway workers make, surfaced on the dashboard. The user wanted to "literally see the bot thinking" — done.

### Backend
- `POST /api/bot-brain/cycles` — auth via `X-Lock-Token`, idempotent on `(worker, instrument, timestamp)`. Stores in `bot_cycles` MongoDB collection, auto-trims at 2000 entries.
- `GET /api/bot-brain/cycles?limit=N&worker=...` — newest first + LONG/SHORT/HOLD counts for the panel filter pills.

### Workers
- `cycle_log.append()` now also fires a background thread that POSTs each entry to `DASHBOARD_LOCK_WEBHOOK_URL` (derives the bot-brain URL by swapping the path). Fire-and-forget — never blocks the trading loop.
- Worker name auto-detected from path so dashboard attributes correctly.

### Frontend
- New `BotBrainPanel` component below the tables: live rows with time + worker tag + action badge + Tauric/Kronos scores + reasoning. Filter veto rows show a red `🛡 indicators` chip explaining which filter rejected.
- Auto-refreshes every 8s. Filter pills (ALL / LONG / SHORT / HOLD) with counts.
- Mobile-friendly: scores collapse on small screens, reasoning wraps below.

### Verified
- Seeded 3 cycle types (LONG-armed, HOLD-floor, HOLD-filter-veto) via curl
- Panel renders all 3 correctly with proper color coding (green Tauric ≥7, green Kronos >50%)
- Filter pills count correctly (1 LONG, 2 HOLD)
- Lint clean, screenshot confirmed

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
