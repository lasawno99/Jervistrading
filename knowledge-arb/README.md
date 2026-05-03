# knowledge-arb

A signal-only Railway worker that watches a list of topics for **early-stage narratives** — real-world shifts visible in the wild but not yet priced into markets — and pushes scored alerts to Telegram.

Does **not** trade. It sends thesis + tickers + risks. You decide what to do.

## How it works

1. For each topic in `WATCHLIST`, fetch recent (24h) news and broader (7d) web results via **Tavily**.
2. Hand the evidence to **Claude** with a strict scoring prompt:
   - `stage`: pre-emerging / emerging / breakout / mainstream / fading
   - `confidence`: 1–10
   - `thesis`: one sentence on what's shifting
   - `tickers`: up to 5 publicly-traded symbols that benefit
   - `risks`: one sentence that would invalidate the thesis
3. Alert if `stage ∈ {pre-emerging, emerging, breakout}` AND `confidence ≥ MIN_CONFIDENCE`.
4. Cooldown: same `(topic, stage)` won't re-alert for 7 days.

## Architecture

```
APScheduler (every 6h)
   │
   ▼
For each topic in WATCHLIST:
   Tavily (news 24h + web 7d) ──► Claude scorer ──► stage + confidence
                                                          │
                                     below threshold ─── no ──► Telegram
                                            │
                                            └── yes ──► log "scored" only
```

## Railway deploy

1. Railway → New Service on the same project → Deploy from GitHub repo.
2. Settings → Source → **Root Directory: `knowledge-arb`**.
3. Variables:
   ```
   ANTHROPIC_API_KEY=...
   ANTHROPIC_MODEL=claude-sonnet-4-6
   TAVILY_API_KEY=...
   TELEGRAM_BOT_TOKEN=...      (share with forex-agent; no polling here)
   TELEGRAM_CHAT_ID=...
   WATCHLIST=AI agents,weight loss drugs,small modular reactors,quantum computing,lithium shortage,stablecoin regulation,robotics automation
   SCHEDULE_CRON=0 */6 * * *
   MIN_CONFIDENCE=7
   ```
4. Deploy.

## Example alert

```
🌱 Knowledge arb — small modular reactors
Stage: emerging · confidence 8/10
Thesis: Hyperscaler AI demand is outpacing grid capacity; SMRs are the only answer that ships this decade.
Tickers: NNE, OKLO, SMR, CEG, VST
Risks: Regulatory delays push first revenue past 2028; hyperscalers build renewables instead.
```

## Tuning the watchlist

Add topics where you think you can see the shift before a Bloomberg terminal does:
- specific supply-chain bottlenecks
- niche regulatory changes
- product launches in B2B verticals you know
- Reddit/X chatter you notice first

Keep topics **specific**. "AI" is too broad; "AI agents" or "AI-native CRM" or "LLM-priced inference" are actionable.
