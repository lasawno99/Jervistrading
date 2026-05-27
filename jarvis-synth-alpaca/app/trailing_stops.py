"""Trailing-stop ratchet.

Runs periodically as a background heartbeat. For each open trade:
  - Compute "R" — the original SL distance (entry - current_sl, abs).
  - Compute "current move" — (current_price - entry), signed.
  - If move ≥ 2R   → trail stop to entry + 1R (locks in 1R of profit).
  - elif move ≥ 1R → move stop to breakeven (lock in zero loss).
  - else            → leave the stop alone.

Ratchet is one-way: we NEVER widen a stop, only tighten it.
This is the difference between "lock in profit" and "give it back".
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

log = logging.getLogger("trailing")


# Trade dicts coming from executor.list_open_trades()
TradeDict = Dict[str, Any]


@dataclass(frozen=True)
class TrailingDecision:
    trade_id: str
    instrument: str
    side: str
    current_sl: Optional[float]
    new_sl: Optional[float]  # None = no change
    reason: str


def decide(
    trade: TradeDict,
    current_price: float,
    move_to_breakeven_at: float = 1.0,
    trail_to_one_r_at: float = 2.0,
) -> TrailingDecision:
    """Pure decision function — no I/O. Easy to pytest.

    move_to_breakeven_at: R-multiple at which we move SL to entry.
    trail_to_one_r_at:    R-multiple at which we trail SL to entry + 1R.
    """
    side = trade["side"]
    entry = float(trade["entry"] or 0)
    sl = trade.get("stop_loss")
    trade_id = str(trade["trade_id"])
    instrument = trade["instrument"]

    if entry <= 0 or sl is None:
        return TrailingDecision(trade_id, instrument, side, sl, None, "no entry or sl")

    # R = original stop distance (always positive)
    r = abs(entry - float(sl))
    if r <= 0:
        return TrailingDecision(trade_id, instrument, side, sl, None, "zero R")

    if side == "buy":
        move = current_price - entry  # positive when in profit
        be_target = entry            # breakeven
        trail_target = entry + r     # +1R locked
    elif side == "sell":
        move = entry - current_price
        be_target = entry
        trail_target = entry - r
    else:
        return TrailingDecision(trade_id, instrument, side, sl, None, "unknown side")

    # Skip if not yet at breakeven trigger
    if move < r * move_to_breakeven_at:
        return TrailingDecision(trade_id, instrument, side, sl, None, "not at breakeven trigger")

    # Decide target
    new_sl: Optional[float] = None
    reason = ""
    if move >= r * trail_to_one_r_at:
        new_sl = trail_target
        reason = f"+{move/r:.2f}R → trail SL to entry ±1R"
    else:
        new_sl = be_target
        reason = f"+{move/r:.2f}R → tighten SL to breakeven"

    # One-way ratchet: only tighten
    if side == "buy" and new_sl <= float(sl):
        return TrailingDecision(trade_id, instrument, side, sl, None, "ratchet: already tighter")
    if side == "sell" and new_sl >= float(sl):
        return TrailingDecision(trade_id, instrument, side, sl, None, "ratchet: already tighter")

    return TrailingDecision(trade_id, instrument, side, sl, new_sl, reason)


async def apply_trailing(
    trades: List[TradeDict],
    price_lookup: Callable[[str], Dict[str, float]],
    update_stop: Callable[[str, float], Dict[str, Any]],
    move_to_breakeven_at: float = 1.0,
    trail_to_one_r_at: float = 2.0,
) -> List[Dict[str, Any]]:
    """Iterate trades, decide trailing action, fire the modifier.

    `price_lookup(instrument)` returns {"bid": float, "ask": float}.
    `update_stop(trade_id, new_sl)` performs the broker API call.
    Both can be sync; we just `to_thread` them if needed.

    Returns a list of result dicts (one per trade) for logging.
    """
    results: List[Dict[str, Any]] = []
    for tr in trades:
        try:
            px = await asyncio.to_thread(price_lookup, tr["instrument"])
            # Use bid for long P/L valuation, ask for shorts (worst case)
            current = px["bid"] if tr["side"] == "buy" else px["ask"]
            d = decide(tr, current, move_to_breakeven_at, trail_to_one_r_at)
            if d.new_sl is None:
                results.append({"trade_id": d.trade_id, "action": "skip", "reason": d.reason})
                continue
            resp = await asyncio.to_thread(update_stop, d.trade_id, d.new_sl)
            results.append({
                "trade_id": d.trade_id, "instrument": d.instrument,
                "action": "tightened", "new_sl": d.new_sl, "old_sl": d.current_sl,
                "reason": d.reason, "broker_resp": resp,
            })
        except Exception as e:
            log.warning("trailing_apply_error trade=%s err=%s", tr.get("trade_id"), e)
            results.append({"trade_id": tr.get("trade_id"), "action": "error", "reason": str(e)})
    return results


async def heartbeat_loop(
    interval_seconds: int,
    list_trades: Callable[[], List[TradeDict]],
    price_lookup: Callable[[str], Dict[str, float]],
    update_stop: Callable[[str, float], Dict[str, Any]],
    on_action: Optional[Callable[[List[Dict[str, Any]]], Awaitable[None]]] = None,
) -> None:
    """Long-running coroutine — list trades, apply trailing, sleep, repeat."""
    while True:
        try:
            trades = await asyncio.to_thread(list_trades)
            if trades:
                results = await apply_trailing(trades, price_lookup, update_stop)
                acted = [r for r in results if r.get("action") == "tightened"]
                if acted:
                    log.info("trailing_acted count=%d details=%s", len(acted), acted)
                    if on_action:
                        try:
                            await on_action(acted)
                        except Exception as e:
                            log.warning("trailing_on_action_error: %s", e)
        except Exception as e:
            log.warning("trailing_loop_error: %s", e)
        await asyncio.sleep(interval_seconds)
