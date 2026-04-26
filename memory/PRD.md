# JARVIS // Trade Center — PRD

## Original Problem Statement
> "Build a Jarvis-style repo: an agent in the center that spawns throughout the dashboard and runs tasks like trading, watches Twitter, schedules meetings, etc."
> Refined: a 24/7 Telegram-connected paper trading bot powered by **Kimi K2.5**, with a Jarvis-style dashboard as the live monitor view.

## Architecture
- **Backend**: FastAPI (`/app/backend/server.py`) + MongoDB (motor). Background asyncio tasks for Telegram long-polling and the auto-trader loop.
- **Trading engine** (`/app/backend/trading_engine.py`): in-memory random-walk price feed for BTC/ETH/OIL/GOLD/TSLA/NVDA, paper account, positions, trades, AI signals.
- **Telegram bot** (`/app/backend/telegram_bot.py`): raw httpx long-polling, inline-keyboard signal approvals, /start /status /auto /buy /sell /signal /trades commands.
- **Frontend**: React 19 single-page Jarvis HUD (`/app/frontend/src/App.js`) — central orb + 8 glassmorphic panels + bottom command palette + browser STT/TTS.

## Personas
- **Solo trader / quant hobbyist** wants 24/7 AI-assisted paper trading via Telegram while glancing at a futuristic dashboard.

## Static core requirements
- Central glowing AI orb (idle/listening/thinking states).
- Voice command palette (Web Speech API) + TTS replies.
- Live updating panels (auto-refresh every 4-5s).
- Telegram approve/skip flow for AI signals.
- Manual buy/sell from dashboard.
- Auto-trader toggle (90s loop).
- Cyberpunk dark aesthetic — Chakra Petch + IBM Plex Mono, electric cyan/magenta/amber on deep navy.

## Implemented (2026-04-26)
- Backend: `/api/chat`, `/api/tasks`, `/api/feed/{trading,twitter,calendar,news}`, `/api/bot/{status,positions,trades,signals,signal,signal/{id}/{approve,skip},trade,auto,reset}`.
- Kimi K2.5 integration via Moonshot OpenAI-compatible API (`https://api.moonshot.ai/v1`). Strict mode returns None when no key → caller uses heuristic fallback.
- Telegram polling + auto-trader loops scheduled in FastAPI startup.
- Mongo collections: `messages`, `tasks`, `paper_account`, `paper_positions`, `paper_trades`, `signals`.
- Frontend: 8 panels (BotPositions, Trading, Schedule, AI Signals, Bot Control, X Feed, News, plus Tasks via panel reuse), JarvisOrb (CSS/SVG), CommandPalette with mic, HUD top bar w/ status indicators, grain + scan-line overlays.

## Backlog / Next
- **P0**: User to add real `MOONSHOT_API_KEY` and `TELEGRAM_BOT_TOKEN` to `backend/.env` and restart backend.
- **P1**: Wire Binance testnet (real prices + paper orders) instead of random-walk mock.
- **P1**: Persist subscribed Telegram chats to Mongo (currently in-memory, lost on restart).
- **P2**: Risk controls (max position size, daily loss limit, kill switch).
- **P2**: Equity curve chart + per-symbol P/L history.
- **P2**: Drag-to-rearrange panels.
- **P2**: Push Twitter/X real feed via X API v2.

## Key files
- `/app/backend/server.py` — FastAPI app, routes, Kimi calls.
- `/app/backend/trading_engine.py` — paper trading + signal generation.
- `/app/backend/telegram_bot.py` — Telegram polling + commands.
- `/app/frontend/src/App.js` — main shell + voice + chat.
- `/app/frontend/src/components/{JarvisOrb,Panel,CommandPalette}.jsx`.
- `/app/frontend/src/components/panels/*.jsx`.
