"""Backtest engine — replay the JARVIS signal pipeline against historical data.

Self-contained: this lives in the dashboard backend, NOT the Railway workers, so
the workers stay deployable independently. It re-implements the *deterministic*
parts of the pipeline (Kronos surrogate, ATR sizing, filters, sizer, trailing)
in pure numpy/pandas. The probabilistic Tauric 7-agent debate is optional —
gated behind use_tauric=True so backtest runs stay fast and cheap.

Data via yfinance (free, no API key). Stores results in MongoDB.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger("backtest")


# ---------- symbol mapping --------------------------------------------------

# Map JARVIS-style symbols to yfinance tickers
SYMBOL_MAP = {
    # Forex
    "EUR_USD": "EURUSD=X", "GBP_USD": "GBPUSD=X", "USD_JPY": "USDJPY=X",
    "AUD_USD": "AUDUSD=X", "USD_CHF": "USDCHF=X", "NZD_USD": "NZDUSD=X",
    "USD_CAD": "USDCAD=X", "EUR_GBP": "EURGBP=X", "EUR_JPY": "EURJPY=X",
    "XAU_USD": "GC=F",  # gold futures as proxy
    # Crypto
    "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "SOL/USD": "SOL-USD",
    "AVAX/USD": "AVAX-USD", "LTC/USD": "LTC-USD", "LINK/USD": "LINK-USD",
    # Stocks pass-through
    "NVDA": "NVDA", "TSLA": "TSLA", "AAPL": "AAPL",
    "AMD": "AMD", "META": "META", "MSFT": "MSFT",
}


def map_symbol(sym: str) -> str:
    return SYMBOL_MAP.get(sym.upper(), sym)


# ---------- indicators (mirror /app/jarvis-synth/app/indicators.py) ---------

def _ema(values: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0.0
    tr = np.maximum.reduce([
        highs[1:] - lows[1:],
        np.abs(highs[1:] - closes[:-1]),
        np.abs(lows[1:] - closes[:-1]),
    ])
    alpha = 1.0 / period
    val = tr[0]
    for x in tr[1:]:
        val = alpha * x + (1 - alpha) * val
    return float(val)


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    diffs = np.diff(closes)
    gains = np.where(diffs > 0, diffs, 0.0)[-period:]
    losses = np.where(diffs < 0, -diffs, 0.0)[-period:]
    avg_g = gains.mean() if len(gains) else 0
    avg_l = losses.mean() if len(losses) else 0
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return float(100.0 - (100.0 / (1.0 + rs)))


# ---------- Kronos surrogate ------------------------------------------------

def kronos_surrogate(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> Dict[str, Any]:
    """Cheap, deterministic stand-in for the Kronos NN forecaster.

    Uses EMA-9 over EMA-20 momentum + recent slope to derive an upside_prob
    in [0,1]. NOT a substitute for the real Kronos NN — used in backtest only
    so we can validate the surrounding pipeline (filters + sizer + ATR + trail)
    without spinning up the NN per bar.
    """
    if len(closes) < 30:
        return {"direction": "skip", "confidence": "low", "upside_prob": 0.5, "vol_amp": 1.0}

    ema9 = _ema(closes[-30:], 9)[-1]
    ema20 = _ema(closes[-30:], 20)[-1]
    slope = (_ema(closes[-30:], 20)[-1] - _ema(closes[-30:], 20)[-5]) / max(1e-9, ema20)

    # Map momentum to upside probability
    momentum = (ema9 - ema20) / max(1e-9, ema20)
    upside_prob = 0.5 + max(-0.45, min(0.45, momentum * 12 + slope * 8))

    # vol_amp = recent stddev vs historical
    recent = closes[-20:]
    older = closes[-100:-20] if len(closes) >= 100 else closes[:-20]
    recent_std = float(np.std(np.diff(recent) / recent[:-1])) if len(recent) > 5 else 0
    older_std = float(np.std(np.diff(older) / older[:-1])) if len(older) > 5 else recent_std
    vol_amp = (recent_std / older_std) if older_std > 0 else 1.0

    if vol_amp > 2.0:
        return {"direction": "skip", "confidence": "low", "upside_prob": upside_prob, "vol_amp": vol_amp}

    if upside_prob >= 0.70:
        direction = "buy"
        confidence = "high" if upside_prob >= 0.80 else "medium"
    elif upside_prob <= 0.30:
        direction = "sell"
        confidence = "high" if upside_prob <= 0.20 else "medium"
    else:
        direction = "skip"
        confidence = "low"

    return {
        "direction": direction, "confidence": confidence,
        "upside_prob": upside_prob, "vol_amp": vol_amp,
    }


# ---------- filters (mirror filters.py logic) -------------------------------

def mtf_trend_agree(direction: str, primary_closes: np.ndarray, mtf_closes: np.ndarray) -> bool:
    if direction == "skip" or len(primary_closes) < 25 or len(mtf_closes) < 25:
        return True
    p_ema = _ema(primary_closes[-30:], 20)
    p_slope = p_ema[-1] - p_ema[-5]
    m_ema = _ema(mtf_closes[-30:], 20)
    m_slope = m_ema[-1] - m_ema[-5]
    if direction == "buy":
        return p_slope > 0 and m_slope > 0
    return p_slope < 0 and m_slope < 0


def indicator_confluence(direction: str, closes: np.ndarray) -> bool:
    if direction == "skip" or len(closes) < 35:
        return True
    rsi = _rsi(closes)
    if direction == "buy":
        return rsi < 70 and closes[-1] > _ema(closes[-30:], 20)[-1]
    return rsi > 30 and closes[-1] < _ema(closes[-30:], 20)[-1]


# ---------- synth + sizer (mirror) ------------------------------------------

_MATRIX = {
    "BUY": {"buy": "full", "sell": "none", "skip": "half"},
    "OVERWEIGHT": {"buy": "half", "sell": "none", "skip": "none"},
    "HOLD": {"buy": "none", "sell": "none", "skip": "none"},
    "UNDERWEIGHT": {"buy": "none", "sell": "half", "skip": "none"},
    "SELL": {"buy": "none", "sell": "full", "skip": "half"},
}


def synthesize(tauric_verdict: str, tauric_conf: int, kronos: Dict[str, Any], base_units: int) -> Dict[str, Any]:
    if tauric_conf < 8 or kronos["confidence"] == "low":
        return {"action": "HOLD", "units": 0, "reason": f"floor: T={tauric_conf} K={kronos['confidence']}"}
    sizing = _MATRIX.get(tauric_verdict, {}).get(kronos["direction"], "none")
    if sizing == "none":
        return {"action": "HOLD", "units": 0, "reason": "matrix none"}
    if sizing == "half":
        units = max(1, base_units // 2)
    else:
        units = base_units
    is_short = tauric_verdict in ("SELL", "UNDERWEIGHT") or kronos["direction"] == "sell"
    return {
        "action": "SHORT" if is_short else "LONG",
        "units": units,
        "reason": f"{tauric_verdict}/{tauric_conf}+{kronos['direction']}/{kronos['confidence']}={sizing}",
    }


_CONV_MULT = {7: 1.0, 8: 1.3, 9: 1.6, 10: 2.0}


def size_position(base_units: int, conf: int, vol_amp: float) -> int:
    if base_units <= 0:
        return 0
    c = _CONV_MULT.get(int(max(7, min(10, conf))), 1.0)
    if vol_amp >= 2.0:
        return 0
    v = 0.5 if vol_amp > 1.3 else 1.0
    return max(1, int(round(base_units * c * v)))


# ---------- Tauric LLM (Smart mode only) ------------------------------------

async def tauric_quick_vote(symbol: str, kronos: Dict[str, Any], recent_change_pct: float) -> Optional[Dict[str, Any]]:
    """Lightweight Tauric surrogate using a single LLM call (not the full 7-agent debate).

    Used only when use_tauric=True. Returns {verdict, confidence} or None on failure.
    """
    import os
    try:
        import anthropic  # type: ignore
    except Exception:
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return None

    prompt = (
        f"You are a single risk-manager voting on a single trade. Reply with EXACTLY one line: "
        f"<VERDICT>|<CONFIDENCE>\n"
        f"VERDICT must be BUY, OVERWEIGHT, HOLD, UNDERWEIGHT, or SELL.\n"
        f"CONFIDENCE is an int 1-10.\n\n"
        f"Symbol: {symbol}\n"
        f"Kronos direction: {kronos['direction']} (upside_prob={kronos['upside_prob']:.2%}, vol_amp={kronos['vol_amp']:.2f}x)\n"
        f"Recent 24-bar return: {recent_change_pct:+.2%}\n"
        f"Reply only with the single line."
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = await asyncio.to_thread(
            client.messages.create,
            model="claude-sonnet-4-20250514",
            max_tokens=40,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip().split("\n")[0]
        if "|" not in text:
            return None
        v, c = text.split("|", 1)
        verdict = v.strip().upper()
        confidence = int(c.strip())
        if verdict not in _MATRIX or confidence < 1 or confidence > 10:
            return None
        return {"verdict": verdict, "confidence": confidence}
    except Exception as e:
        log.warning("tauric_quick_vote error: %s", e)
        return None


def tauric_deterministic(kronos: Dict[str, Any]) -> Dict[str, Any]:
    """No-LLM stand-in — uses Kronos signal strength to assign a verdict + confidence."""
    p = kronos["upside_prob"]
    if p >= 0.80:
        return {"verdict": "BUY", "confidence": 9}
    if p >= 0.70:
        return {"verdict": "OVERWEIGHT", "confidence": 8}
    if p <= 0.20:
        return {"verdict": "SELL", "confidence": 9}
    if p <= 0.30:
        return {"verdict": "UNDERWEIGHT", "confidence": 8}
    return {"verdict": "HOLD", "confidence": 6}


# ---------- backtest engine -------------------------------------------------

@dataclass
class TradeRecord:
    bar_idx: int
    entry_time: str
    entry_price: float
    side: str
    units: int
    sl: float
    tp: float
    exit_time: str = ""
    exit_price: float = 0.0
    exit_reason: str = ""  # tp | sl | trailing | end
    pl_pct: float = 0.0


@dataclass
class BacktestResult:
    run_id: str
    symbol: str
    yf_symbol: str
    bars: int
    use_tauric: bool
    trades: List[Dict[str, Any]] = field(default_factory=list)
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    expectancy: float = 0.0
    total_pl_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    elapsed_seconds: float = 0.0
    started_at: str = ""
    finished_at: str = ""
    error: Optional[str] = None


def _fetch_bars(yf_symbol: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch via yfinance — module imported lazily."""
    import yfinance as yf
    df = yf.download(
        yf_symbol, period=period, interval=interval,
        progress=False, auto_adjust=False, threads=False,
    )
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned no data for {yf_symbol}")
    df = df.reset_index()
    # Normalize column names — yfinance returns ['Open','High','Low','Close','Adj Close','Volume']
    df.columns = [str(c).lower() if not isinstance(c, tuple) else str(c[0]).lower() for c in df.columns]
    return df


async def run_backtest(
    symbol: str,
    period: str = "60d",
    interval: str = "1h",
    base_units: int = 1000,
    use_tauric: bool = False,
    max_llm_calls: int = 50,
) -> BacktestResult:
    """Run a backtest. Returns a BacktestResult ready to persist."""
    run_id = uuid.uuid4().hex[:12]
    started = datetime.now(timezone.utc)
    yf_symbol = map_symbol(symbol)

    result = BacktestResult(
        run_id=run_id, symbol=symbol, yf_symbol=yf_symbol,
        bars=0, use_tauric=use_tauric, started_at=started.isoformat(),
    )

    try:
        df = await asyncio.to_thread(_fetch_bars, yf_symbol, period, interval)
    except Exception as e:
        result.error = f"fetch_failed: {e}"
        result.finished_at = datetime.now(timezone.utc).isoformat()
        return result

    df = df.dropna(subset=["close", "high", "low"]).reset_index(drop=True)
    result.bars = len(df)
    if len(df) < 50:
        result.error = "not_enough_bars"
        result.finished_at = datetime.now(timezone.utc).isoformat()
        return result

    closes = df["close"].astype(float).to_numpy()
    highs = df["high"].astype(float).to_numpy()
    lows = df["low"].astype(float).to_numpy()
    times = df["datetime"].astype(str).tolist() if "datetime" in df.columns else df.iloc[:, 0].astype(str).tolist()

    # MTF surrogate: re-sample to 4x interval by averaging closes in 4-bar windows.
    # Cheap approximation; for backtest validation this is OK.
    def _mtf_closes(i):
        win = closes[max(0, i - 120):i + 1]
        # collapse to ~30 "4-hour" bars
        return np.array([win[max(0, j - 3):j + 1].mean() for j in range(0, len(win), 4) if j > 0])

    trades: List[TradeRecord] = []
    open_trade: Optional[TradeRecord] = None
    llm_calls = 0
    equity = 1.0
    equity_curve = [equity]
    peak_equity = 1.0
    max_dd = 0.0

    # We walk bars [40, len-1]; the last bar can't form a fresh trade (no future)
    for i in range(40, len(df) - 1):
        # Handle exit on existing trade first using bar i's high/low
        if open_trade is not None:
            hi = highs[i]
            lo = lows[i]
            exited = False
            if open_trade.side == "LONG":
                if lo <= open_trade.sl:
                    open_trade.exit_price = open_trade.sl
                    open_trade.exit_reason = "sl"
                    exited = True
                elif hi >= open_trade.tp:
                    open_trade.exit_price = open_trade.tp
                    open_trade.exit_reason = "tp"
                    exited = True
            else:  # SHORT
                if hi >= open_trade.sl:
                    open_trade.exit_price = open_trade.sl
                    open_trade.exit_reason = "sl"
                    exited = True
                elif lo <= open_trade.tp:
                    open_trade.exit_price = open_trade.tp
                    open_trade.exit_reason = "tp"
                    exited = True
            if exited:
                open_trade.exit_time = times[i]
                if open_trade.side == "LONG":
                    open_trade.pl_pct = (open_trade.exit_price - open_trade.entry_price) / open_trade.entry_price * 100
                else:
                    open_trade.pl_pct = (open_trade.entry_price - open_trade.exit_price) / open_trade.entry_price * 100
                equity *= (1 + open_trade.pl_pct / 100)
                equity_curve.append(equity)
                peak_equity = max(peak_equity, equity)
                dd = (peak_equity - equity) / peak_equity * 100
                max_dd = max(max_dd, dd)
                trades.append(open_trade)
                open_trade = None
            else:
                continue  # one trade at a time

        # No open trade — look for new entry
        h = closes[:i + 1]
        kronos = kronos_surrogate(h, highs[:i + 1], lows[:i + 1])
        if kronos["direction"] == "skip":
            continue
        mtf = _mtf_closes(i)
        if not mtf_trend_agree(kronos["direction"], h, mtf):
            continue
        if not indicator_confluence(kronos["direction"], h):
            continue

        # Tauric — either Smart-mode LLM call (budget-capped) or deterministic stand-in
        if use_tauric and llm_calls < max_llm_calls:
            recent_change = (h[-1] - h[-24]) / h[-24] if len(h) >= 25 else 0
            vote = await tauric_quick_vote(symbol, kronos, recent_change)
            llm_calls += 1
            if vote is None:
                vote = tauric_deterministic(kronos)
        else:
            vote = tauric_deterministic(kronos)

        decision = synthesize(vote["verdict"], vote["confidence"], kronos, base_units)
        if decision["action"] == "HOLD":
            continue

        sized = size_position(decision["units"], vote["confidence"], kronos["vol_amp"])
        if sized <= 0:
            continue

        # Entry at next bar open (i+1)
        entry = closes[i]
        atr = _atr(highs[max(0, i - 30):i + 1], lows[max(0, i - 30):i + 1], h[max(0, i - 30):i + 1])
        sl_dist = max(atr * 1.5, entry * 0.003)  # at least 0.3% to avoid degenerate stops
        rr = 3.0 if vote["confidence"] >= 9 else (2.5 if vote["confidence"] >= 8 else 2.0)
        tp_dist = sl_dist * rr

        if decision["action"] == "LONG":
            sl = entry - sl_dist
            tp = entry + tp_dist
        else:
            sl = entry + sl_dist
            tp = entry - tp_dist

        open_trade = TradeRecord(
            bar_idx=i, entry_time=times[i], entry_price=entry,
            side=decision["action"], units=sized, sl=sl, tp=tp,
        )

    # Close any open trade at the last bar
    if open_trade is not None:
        last = closes[-1]
        open_trade.exit_price = last
        open_trade.exit_reason = "end"
        open_trade.exit_time = times[-1]
        if open_trade.side == "LONG":
            open_trade.pl_pct = (last - open_trade.entry_price) / open_trade.entry_price * 100
        else:
            open_trade.pl_pct = (open_trade.entry_price - last) / open_trade.entry_price * 100
        equity *= (1 + open_trade.pl_pct / 100)
        trades.append(open_trade)

    # Aggregate
    wins = [t for t in trades if t.pl_pct > 0]
    losses = [t for t in trades if t.pl_pct <= 0]
    result.trades = [asdict(t) for t in trades]
    result.total_trades = len(trades)
    result.wins = len(wins)
    result.losses = len(losses)
    result.win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    result.total_pl_pct = (equity - 1.0) * 100
    result.avg_win_pct = float(np.mean([t.pl_pct for t in wins])) if wins else 0.0
    result.avg_loss_pct = float(np.mean([t.pl_pct for t in losses])) if losses else 0.0
    result.expectancy = (
        (result.win_rate / 100.0) * result.avg_win_pct
        + ((1 - result.win_rate / 100.0)) * result.avg_loss_pct
    )
    result.max_drawdown_pct = max_dd
    result.elapsed_seconds = (datetime.now(timezone.utc) - started).total_seconds()
    result.finished_at = datetime.now(timezone.utc).isoformat()
    return result
