"""FX strategy engine — backtests + live runners.

Strategy logic ported from trentstauff/FXBot (vectorized numpy/pandas),
but decoupled from tpqoa/matplotlib. Uses our oanda_client for data.

Backtests work in two modes:
- synthetic: random-walk price series (no creds needed, instant demo)
- oanda: real OANDA M1/H1/D1 candles via httpx (needs OANDA_API_TOKEN)

Live strategies run as asyncio tasks, poll price every N seconds,
emit signals, place market orders via oanda_client. State persisted
to Mongo `live_strategies` and auto-resumed on startup.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal

import numpy as np
import pandas as pd
import httpx

import oanda_client as oa

logger = logging.getLogger("fx-strategies")

GRANULARITY_MAP = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "4h", "D": "1D"}


# ---------------- Data acquisition ----------------

def _synthetic_series(instrument: str, start: str, end: str, granularity: str = "H1", seed: Optional[int] = None) -> pd.DataFrame:
    """Random-walk price series with realistic drift and vol."""
    rng = np.random.default_rng(seed if seed is not None else hash((instrument, start, end, granularity)) & 0xFFFFFFFF)
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    freq = GRANULARITY_MAP.get(granularity, "1H")
    idx = pd.date_range(start_dt, end_dt, freq=freq)
    n = len(idx)
    if n < 50:
        idx = pd.date_range(start_dt, periods=200, freq=freq)
        n = 200
    base_price = oa._MOCK_PRICES.get(instrument, (1.0, 1.0))[0]
    vol = 0.0008 if "JPY" not in instrument else 0.05
    returns = rng.normal(0, vol, n)
    prices = base_price * np.exp(np.cumsum(returns))
    return pd.DataFrame({"price": prices}, index=idx)


def _oanda_candles(instrument: str, start: str, end: str, granularity: str = "H1") -> pd.DataFrame:
    """Fetch real OANDA candles via httpx. Returns DataFrame indexed by UTC datetime with `price` (close) col."""
    if not oa.is_configured():
        raise RuntimeError("OANDA not configured")
    inst = oa._normalize_instrument(instrument)
    base = oa._base_url()
    headers = oa._headers()
    params = {
        "from": start, "to": end, "granularity": granularity, "price": "M",
    }
    r = httpx.get(f"{base}/v3/instruments/{inst}/candles", headers=headers, params=params, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"OANDA candles error: {r.status_code} {r.text[:200]}")
    candles = r.json().get("candles", [])
    rows = []
    for c in candles:
        if not c.get("complete"):
            continue
        rows.append({"time": c["time"], "price": float(c["mid"]["c"])})
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame({"price": []})
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time")
    return df


def get_price_series(instrument: str, start: str, end: str, granularity: str = "H1", source: str = "auto") -> tuple[pd.DataFrame, str]:
    """source: 'auto'|'synthetic'|'oanda'. Returns (df, source_used)."""
    if source == "synthetic":
        return _synthetic_series(instrument, start, end, granularity), "synthetic"
    if source == "oanda":
        return _oanda_candles(instrument, start, end, granularity), "oanda"
    # auto
    if oa.is_configured():
        try:
            df = _oanda_candles(instrument, start, end, granularity)
            if not df.empty:
                return df, "oanda"
        except Exception as e:
            logger.warning(f"oanda fetch failed, falling back to synthetic: {e}")
    return _synthetic_series(instrument, start, end, granularity), "synthetic"


# ---------------- Backtest engine (vectorized, ported from FXBot logic) ----------------

def _stats_from_returns(df: pd.DataFrame, trading_cost: float = 0.0) -> dict:
    """df must have `returns` and `strategy` (= position * returns) columns."""
    if df.empty:
        return {"return_pct": 0, "outperformance_pct": 0, "trades": 0, "sharpe": 0, "win_rate": 0}
    pos = df["position"].fillna(0)
    trades = (pos.diff().abs() > 0).sum()
    df["strategy_net"] = df["strategy"] - trading_cost * (pos.diff().abs())
    cum_strat = np.exp(df["strategy_net"].cumsum()).iloc[-1] - 1
    cum_bh = np.exp(df["returns"].cumsum()).iloc[-1] - 1
    out_perf = cum_strat - cum_bh
    sharpe = (df["strategy_net"].mean() / df["strategy_net"].std() * np.sqrt(252 * 24)) if df["strategy_net"].std() > 0 else 0
    wins = (df.loc[pos != 0, "strategy_net"] > 0).sum()
    losses = (df.loc[pos != 0, "strategy_net"] < 0).sum()
    win_rate = wins / max(1, wins + losses)
    return {
        "return_pct": round(cum_strat * 100, 3),
        "buy_hold_pct": round(cum_bh * 100, 3),
        "outperformance_pct": round(out_perf * 100, 3),
        "trades": int(trades),
        "sharpe": round(float(sharpe), 3),
        "win_rate": round(float(win_rate), 3),
    }


def backtest_sma(instrument: str, start: str, end: str, smas: int = 20, smal: int = 50,
                 granularity: str = "H1", trading_cost: float = 0.0, source: str = "auto") -> dict:
    df, src = get_price_series(instrument, start, end, granularity, source)
    if df.empty:
        return {"error": "empty data"}
    df = df.copy()
    df["returns"] = np.log(df["price"] / df["price"].shift(1))
    df["smas"] = df["price"].rolling(smas).mean()
    df["smal"] = df["price"].rolling(smal).mean()
    df["position"] = np.where(df["smas"] > df["smal"], 1, -1)
    df["position"] = df["position"].shift(1)
    df["strategy"] = df["position"] * df["returns"]
    df = df.dropna()
    return {"strategy": "SMA", "instrument": instrument, "smas": smas, "smal": smal,
            "granularity": granularity, "source": src, **_stats_from_returns(df, trading_cost)}


def backtest_bollinger(instrument: str, start: str, end: str, sma: int = 20, deviation: float = 2,
                       granularity: str = "H1", trading_cost: float = 0.0, source: str = "auto") -> dict:
    df, src = get_price_series(instrument, start, end, granularity, source)
    if df.empty:
        return {"error": "empty data"}
    df = df.copy()
    df["returns"] = np.log(df["price"] / df["price"].shift(1))
    df["sma"] = df["price"].rolling(sma).mean()
    df["std"] = df["price"].rolling(sma).std()
    df["upper"] = df["sma"] + deviation * df["std"]
    df["lower"] = df["sma"] - deviation * df["std"]
    df["distance"] = df["price"] - df["sma"]
    df["position"] = np.where(df["price"] < df["lower"], 1,
                       np.where(df["price"] > df["upper"], -1, np.nan))
    df["position"] = np.where(df["distance"] * df["distance"].shift(1) < 0, 0, df["position"])
    df["position"] = df["position"].ffill().fillna(0).shift(1)
    df["strategy"] = df["position"] * df["returns"]
    df = df.dropna()
    return {"strategy": "Bollinger", "instrument": instrument, "sma": sma, "deviation": deviation,
            "granularity": granularity, "source": src, **_stats_from_returns(df, trading_cost)}


def backtest_contrarian(instrument: str, start: str, end: str, window: int = 3,
                        granularity: str = "H1", trading_cost: float = 0.0, source: str = "auto") -> dict:
    df, src = get_price_series(instrument, start, end, granularity, source)
    if df.empty:
        return {"error": "empty data"}
    df = df.copy()
    df["returns"] = np.log(df["price"] / df["price"].shift(1))
    df["position"] = -np.sign(df["returns"].rolling(window).mean()).shift(1)
    df["strategy"] = df["position"] * df["returns"]
    df = df.dropna()
    return {"strategy": "Contrarian", "instrument": instrument, "window": window,
            "granularity": granularity, "source": src, **_stats_from_returns(df, trading_cost)}


def backtest_momentum(instrument: str, start: str, end: str, window: int = 3,
                      granularity: str = "H1", trading_cost: float = 0.0, source: str = "auto") -> dict:
    df, src = get_price_series(instrument, start, end, granularity, source)
    if df.empty:
        return {"error": "empty data"}
    df = df.copy()
    df["returns"] = np.log(df["price"] / df["price"].shift(1))
    df["position"] = np.sign(df["returns"].rolling(window).mean()).shift(1)
    df["strategy"] = df["position"] * df["returns"]
    df = df.dropna()
    return {"strategy": "Momentum", "instrument": instrument, "window": window,
            "granularity": granularity, "source": src, **_stats_from_returns(df, trading_cost)}


def backtest_ml_classification(instrument: str, start: str, end: str, lags: int = 5,
                               granularity: str = "H1", trading_cost: float = 0.0,
                               train_split: float = 0.7, source: str = "auto") -> dict:
    """Logistic regression classifier predicting next-bar direction from `lags` previous returns."""
    from sklearn.linear_model import LogisticRegression
    df, src = get_price_series(instrument, start, end, granularity, source)
    if df.empty or len(df) < (lags + 50):
        return {"error": f"need ≥{lags + 50} bars, got {len(df)}"}
    df = df.copy()
    df["returns"] = np.log(df["price"] / df["price"].shift(1))
    cols = []
    for k in range(1, lags + 1):
        c = f"lag_{k}"
        df[c] = df["returns"].shift(k)
        cols.append(c)
    df["direction"] = np.where(df["returns"] > 0, 1, -1)
    df = df.dropna()
    split_idx = int(len(df) * train_split)
    train = df.iloc[:split_idx]
    test = df.iloc[split_idx:].copy()
    if len(train) < 30 or len(test) < 5:
        return {"error": "insufficient train/test split"}
    model = LogisticRegression(C=1e6, max_iter=1000)
    model.fit(train[cols], train["direction"])
    test["position"] = model.predict(test[cols])
    test["strategy"] = test["position"] * test["returns"]
    test = test.rename_axis("time")
    return {"strategy": "ML_Classification", "instrument": instrument, "lags": lags,
            "granularity": granularity, "train_bars": len(train), "test_bars": len(test),
            "source": src, **_stats_from_returns(test, trading_cost)}


# ---------------- Live strategies ----------------

# In-process registry of running asyncio tasks: {strategy_id: asyncio.Task}
_running_tasks: dict = {}


async def _eval_signal(instrument: str, kind: str, params: dict, history: list[float]) -> int:
    """Evaluate signal from price history. Returns 1 (long), -1 (short), 0 (flat)."""
    if len(history) < 5:
        return 0
    arr = np.array(history)
    if kind == "SMA":
        s = params.get("smas", 5)
        lng = params.get("smal", 20)
        if len(arr) < lng:
            return 0
        smas = arr[-s:].mean()
        smal = arr[-lng:].mean()
        return 1 if smas > smal else -1
    if kind == "Bollinger":
        n = params.get("sma", 20)
        d = params.get("deviation", 2.0)
        if len(arr) < n:
            return 0
        m = arr[-n:].mean()
        sd = arr[-n:].std()
        last = arr[-1]
        if last < m - d * sd:
            return 1
        if last > m + d * sd:
            return -1
        return 0
    if kind == "Contrarian":
        w = params.get("window", 3)
        if len(arr) < w + 1:
            return 0
        rets = np.diff(np.log(arr[-(w + 1):]))
        return -int(np.sign(rets.mean()))
    if kind == "Momentum":
        w = params.get("window", 3)
        if len(arr) < w + 1:
            return 0
        rets = np.diff(np.log(arr[-(w + 1):]))
        return int(np.sign(rets.mean()))
    return 0


async def _live_loop(db, strategy_id: str):
    """Poll price every N seconds, evaluate, place orders. Persists state to Mongo."""
    sdoc = await db.live_strategies.find_one({"id": strategy_id})
    if not sdoc:
        return
    inst = sdoc["instrument"]
    kind = sdoc["kind"]
    params = sdoc.get("params", {})
    units = sdoc.get("units", 1000)
    poll_sec = sdoc.get("poll_sec", 30)
    history: list[float] = list(sdoc.get("price_history", []))
    cur_pos = sdoc.get("current_position", 0)  # -1, 0, 1

    logger.info(f"Live strategy {strategy_id} ({kind} on {inst}) started")
    await db.live_strategies.update_one(
        {"id": strategy_id}, {"$set": {"status": "running", "started_at": datetime.now(timezone.utc).isoformat()}}
    )

    try:
        while True:
            try:
                price_data = oa.get_price(inst)
                if "error" in price_data:
                    logger.warning(f"{strategy_id}: price error {price_data['error']}")
                    await asyncio.sleep(poll_sec)
                    continue
                mid = (price_data["bid"] + price_data["ask"]) / 2
                history.append(mid)
                history = history[-200:]  # cap memory
                signal = await _eval_signal(inst, kind, params, history)

                action = None
                trade_result = None
                if signal != cur_pos:
                    # Close existing if any, then open new
                    if cur_pos != 0:
                        oa.close_position(inst, "all")
                    if signal != 0:
                        order_units = units if signal > 0 else -units
                        trade_result = oa.place_market_order(inst, order_units)
                        action = f"{'BUY' if signal > 0 else 'SELL'} {abs(order_units)} {inst} @ {mid:.5f}"
                    else:
                        action = f"FLAT {inst} @ {mid:.5f}"
                    cur_pos = signal
                    await db.strategy_events.insert_one({
                        "id": str(uuid.uuid4()),
                        "strategy_id": strategy_id,
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "action": action,
                        "signal": signal,
                        "price": mid,
                        "trade_result": trade_result,
                    })
                    logger.info(f"{strategy_id}: {action}")

                await db.live_strategies.update_one(
                    {"id": strategy_id},
                    {"$set": {
                        "current_position": cur_pos,
                        "last_price": mid,
                        "last_tick": datetime.now(timezone.utc).isoformat(),
                        "price_history": history[-50:],  # persist tail only
                    }},
                )
            except Exception:
                logger.exception(f"{strategy_id} tick error")
            await asyncio.sleep(poll_sec)
    except asyncio.CancelledError:
        logger.info(f"Live strategy {strategy_id} cancelled")
        await db.live_strategies.update_one(
            {"id": strategy_id},
            {"$set": {"status": "stopped", "stopped_at": datetime.now(timezone.utc).isoformat()}},
        )
    finally:
        _running_tasks.pop(strategy_id, None)


async def start_strategy(db, kind: str, instrument: str, params: dict, units: int = 1000, poll_sec: int = 30) -> dict:
    """Persist + spawn an asyncio task running the strategy."""
    if kind not in ("SMA", "Bollinger", "Contrarian", "Momentum"):
        return {"error": f"unsupported live strategy: {kind}"}
    sid = str(uuid.uuid4())
    doc = {
        "id": sid,
        "kind": kind,
        "instrument": oa._normalize_instrument(instrument),
        "params": params,
        "units": int(units),
        "poll_sec": int(poll_sec),
        "status": "starting",
        "current_position": 0,
        "price_history": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.live_strategies.insert_one(doc)
    task = asyncio.create_task(_live_loop(db, sid))
    _running_tasks[sid] = task
    return {"ok": True, "strategy_id": sid, "kind": kind, "instrument": doc["instrument"]}


async def stop_strategy(db, strategy_id: str) -> dict:
    task = _running_tasks.get(strategy_id)
    if task and not task.done():
        task.cancel()
    await db.live_strategies.update_one(
        {"id": strategy_id},
        {"$set": {"status": "stopped", "stopped_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "strategy_id": strategy_id}


async def list_strategies(db) -> list[dict]:
    docs = await db.live_strategies.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return docs


async def list_strategy_events(db, strategy_id: Optional[str] = None, limit: int = 50) -> list[dict]:
    q = {"strategy_id": strategy_id} if strategy_id else {}
    docs = await db.strategy_events.find(q, {"_id": 0}).sort("ts", -1).to_list(limit)
    return docs


async def resume_active_strategies(db) -> int:
    """Restart asyncio tasks for any strategy that was running before shutdown."""
    docs = await db.live_strategies.find({"status": "running"}, {"_id": 0}).to_list(50)
    for d in docs:
        if d["id"] in _running_tasks:
            continue
        task = asyncio.create_task(_live_loop(db, d["id"]))
        _running_tasks[d["id"]] = task
    return len(docs)
