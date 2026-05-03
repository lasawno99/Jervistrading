# kronos-agent

A signal-only Railway worker that runs the open-source [Kronos](https://github.com/shiyu-coder/Kronos) financial forecasting model against OANDA practice candles and publishes high-confidence signals to Telegram.

Does **not** trade. It sends alerts. You decide whether to act (via `@Jervistradebot` / forex-agent).

## Architecture

```
APScheduler (every 4h, M-F)
   │
   ▼
OANDA candles ──► KronosPredictor ──► Monte-Carlo paths
                                            │
                                            ▼
                              build_signal (direction + confidence)
                                            │
                                 skip? ──── no ──► Telegram
```

- Uses `NeoQuasar/Kronos-small` by default (~25M params, CPU-runnable on Railway).
- Caches model weights at `/hf_cache` inside the container.
- Sends messages to the same bot token as forex-agent — but **does not poll**, so no `409 Conflict`.

## Railway deploy

1. Save to GitHub (the `kronos-agent/` folder is already in the monorepo).
2. Railway → New Service (on the same project as forex-agent) → Deploy from GitHub repo.
3. Settings → Source → **Root Directory: `kronos-agent`**.
4. Variables — paste these (copy values from the corresponding Railway service for forex-agent):
   ```
   OANDA_API_TOKEN=...
   OANDA_ACCOUNT_ID=...
   OANDA_ENVIRONMENT=practice
   TELEGRAM_BOT_TOKEN=...     (same as forex-agent is fine; no polling here)
   TELEGRAM_CHAT_ID=...
   INSTRUMENTS=EUR_USD,GBP_USD,XAU_USD
   GRANULARITY=H1
   LOOKBACK=360
   PRED_LEN=24
   SAMPLE_COUNT=20
   SCHEDULE_CRON=0 */4 * * 1-5
   UPSIDE_PROB_HIGH=0.65
   UPSIDE_PROB_LOW=0.35
   MAX_VOL_AMP=2.0
   KRONOS_SIZE=small
   ```
5. Deploy.

## Expected output

Every 4 hours you'll see a log like:

```json
{"event": "signal", "instrument": "EUR_USD", "direction": "buy", "confidence": "medium", "upside_prob": 0.71, "vol_amp": 1.23, "mean_target": 1.0825}
```

If direction is not `skip`, the same signal is pushed to Telegram:

```
🔮 Kronos — EUR_USD
🟢 BUY · confidence: medium
Price: 1.07820 → target: 1.08250 (+0.40%)
Upside prob: 71% · Vol amp: 1.23x
```

## Notes

- First boot downloads the tokenizer + model from HuggingFace (~100MB). Subsequent boots reuse `/hf_cache`.
- Kronos-small on CPU takes ~3–8s per instrument forecast.
- `KRONOS_SIZE=base` is more accurate but 3x slower; bump only if you move to a GPU host.
