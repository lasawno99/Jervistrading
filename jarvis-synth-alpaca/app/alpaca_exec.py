"""LAYER 5 — Alpaca paper-trading executor.

Mirrors OandaExecutor's surface so the rest of the pipeline (synth,
guardrails, profit-lock, daily-report) stays untouched.

Key differences from OANDA:
  - Alpaca has no "practice environment" flag — paper is selected by URL
    (`paper-api.alpaca.markets`). We hard-fail if a non-paper URL is used.
  - Crypto symbols use BTC/USD notation. Stock symbols are bare tickers.
  - Fractional shares allowed (units are floats, not ints).
  - SL/TP fields: bracket orders work for stocks but NOT for crypto on
    paper. For crypto we place a market order without OTOCO and rely on
    profit-lock + daily-loss-limit for risk containment.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

import structlog

from app.guardrails import (
    AccountState,
    GuardrailRejection,
    GuardrailState,
    Order,
    check_order,
    fire_telegram_alert,
)

log = structlog.get_logger()

PAPER_BASE_URL = "https://paper-api.alpaca.markets"


def _is_crypto(symbol: str) -> bool:
    return "/" in symbol


class AlpacaExecutor:
    def __init__(
        self,
        api_key: str,
        secret_key: str,
        base_url: str,
        guardrail_state: GuardrailState,
        min_rr_ratio: float,
        telegram_send: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        if base_url.strip().rstrip("/") != PAPER_BASE_URL:
            raise RuntimeError(
                f"Refusing base_url={base_url!r}; only {PAPER_BASE_URL} allowed"
            )

        from alpaca.trading.client import TradingClient
        from alpaca.data.historical import (
            CryptoHistoricalDataClient,
            StockHistoricalDataClient,
        )

        self._trading = TradingClient(
            api_key=api_key, secret_key=secret_key, paper=True
        )
        self._stock_data = StockHistoricalDataClient(
            api_key=api_key, secret_key=secret_key
        )
        self._crypto_data = CryptoHistoricalDataClient(
            api_key=api_key, secret_key=secret_key
        )
        self._state = guardrail_state
        self._min_rr = min_rr_ratio
        self._telegram_send = telegram_send
        self._day_starting_balance: Optional[float] = None
        self._day_starting_balance_date: Optional[str] = None

    # ------- pricing ----------------------------------------------------

    def get_price(self, symbol: str) -> Dict[str, float]:
        from alpaca.data.requests import (
            CryptoLatestQuoteRequest,
            StockLatestQuoteRequest,
        )

        if _is_crypto(symbol):
            req = CryptoLatestQuoteRequest(symbol_or_symbols=[symbol])
            quotes = self._crypto_data.get_crypto_latest_quote(req)
            q = quotes[symbol]
            return {"bid": float(q.bid_price), "ask": float(q.ask_price)}

        req = StockLatestQuoteRequest(symbol_or_symbols=[symbol], feed="iex")
        quotes = self._stock_data.get_stock_latest_quote(req)
        q = quotes[symbol]
        return {"bid": float(q.bid_price), "ask": float(q.ask_price)}

    def get_account_summary(self) -> Dict[str, Any]:
        a = self._trading.get_account()
        equity = float(a.equity or 0)
        cash = float(a.cash or 0)
        # Alpaca exposes daytrade-equivalent unrealized via long_market_value -
        # equity drift, but for risk math we want unrealized P&L on positions.
        positions = self._trading.get_all_positions()
        unrealized = sum(float(p.unrealized_pl or 0) for p in positions)
        return {
            "balance": cash,
            "nav": equity,
            "unrealized_pl": unrealized,
            "currency": a.currency or "USD",
        }

    def list_positions(self):
        positions = self._trading.get_all_positions()
        out = []
        for p in positions:
            qty = float(p.qty or 0)  # signed: negative for short
            out.append(
                {
                    "instrument": p.symbol,
                    "units": qty,
                    "side": "buy" if qty > 0 else ("sell" if qty < 0 else "flat"),
                    "unrealized_pl": float(p.unrealized_pl or 0),
                }
            )
        return out

    # ------- day baseline ----------------------------------------------

    def reset_day_baseline(self, new_balance: float) -> None:
        from datetime import datetime, timezone

        self._day_starting_balance = float(new_balance)
        self._day_starting_balance_date = datetime.now(timezone.utc).strftime(
            "%Y-%m-%d"
        )
        log.info("day_starting_balance_reset", new_balance=new_balance)

    def _ensure_day_starting_balance(self) -> float:
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._day_starting_balance_date != today:
            s = self.get_account_summary()
            self._day_starting_balance = float(s["nav"])
            self._day_starting_balance_date = today
        return float(self._day_starting_balance or 0.0)

    def _account_state(self) -> AccountState:
        starting = self._ensure_day_starting_balance()
        s = self.get_account_summary()
        unrealized = s["unrealized_pl"]
        realized = s["nav"] - starting - unrealized
        return AccountState(
            starting_balance=starting,
            realized_pl=realized,
            unrealized_pl=unrealized,
        )

    # ------- order placement -------------------------------------------

    def execute(
        self,
        instrument: str,
        side: str,
        units: int,
        rationale: str = "",
        rr_ratio: float = 2.0,
        sl_pips: float = 10.0,
    ) -> Dict[str, Any]:
        """Place a paper market order with a bracket SL/TP for stocks.

        For crypto, brackets aren't supported on Alpaca paper, so we place
        a plain market order; the broader risk engine (profit-lock,
        daily-loss-limit) still bounds drawdown.

        sl_pips here is interpreted as a percent of price for non-FX assets:
        crypto SL distance = price * (sl_pips/100), TP = SL * rr_ratio.
        For stocks the same percent-of-price model applies.
        """
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be buy|sell (got {side!r})")
        if rr_ratio < self._min_rr:
            return {
                "status": "rejected",
                "reason": f"R:R {rr_ratio} < MIN_RR_RATIO {self._min_rr}",
            }

        px = self.get_price(instrument)
        ref = px["ask"] if side == "buy" else px["bid"]

        # Percent-of-price stop: 1.0 → 1% SL distance
        sl_pct = sl_pips / 100.0
        sl_dist = ref * sl_pct
        tp_dist = sl_dist * rr_ratio

        if side == "buy":
            sl = round(ref - sl_dist, 4)
            tp = round(ref + tp_dist, 4)
        else:
            sl = round(ref + sl_dist, 4)
            tp = round(ref - tp_dist, 4)

        order = Order(
            instrument=instrument,
            side=side,
            units=units,
            stop_loss=sl,
            take_profit=tp,
            rationale=rationale,
        )

        on_halt = (
            fire_telegram_alert(self._telegram_send) if self._telegram_send else None
        )
        try:
            check_order(
                order, self._state, self._account_state(), on_daily_halt=on_halt
            )
        except GuardrailRejection as e:
            log.warning("guardrail_rejected", instrument=instrument, reason=str(e))
            return {"status": "rejected", "reason": str(e)}

        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import (
            LimitOrderRequest,
            MarketOrderRequest,
            StopLossRequest,
            TakeProfitRequest,
        )

        alp_side = OrderSide.BUY if side == "buy" else OrderSide.SELL

        try:
            if _is_crypto(instrument):
                # Crypto: market order, no bracket (Alpaca paper limitation)
                req = MarketOrderRequest(
                    symbol=instrument,
                    qty=units,
                    side=alp_side,
                    time_in_force=TimeInForce.GTC,
                )
                resp = self._trading.submit_order(req)
            else:
                # Stocks: bracket order with SL + TP attached
                req = MarketOrderRequest(
                    symbol=instrument,
                    qty=units,
                    side=alp_side,
                    time_in_force=TimeInForce.DAY,
                    order_class="bracket",
                    stop_loss=StopLossRequest(stop_price=str(round(sl, 2))),
                    take_profit=TakeProfitRequest(limit_price=str(round(tp, 2))),
                )
                resp = self._trading.submit_order(req)
        except Exception as e:
            log.error("alpaca_order_failed", instrument=instrument, error=str(e))
            return {"status": "error", "reason": str(e)}

        fill_price = (
            float(resp.filled_avg_price)
            if getattr(resp, "filled_avg_price", None)
            else None
        )
        log.info(
            "alpaca_order_placed",
            instrument=instrument,
            side=side,
            units=units,
            order_id=str(resp.id),
            sl=sl,
            tp=tp,
            fill_price=fill_price,
        )
        return {
            "status": str(resp.status).split(".")[-1].lower()
            if hasattr(resp, "status")
            else "submitted",
            "instrument": instrument,
            "side": side,
            "units": units,
            "stop_loss": sl,
            "take_profit": tp,
            "fill_price": fill_price,
            "transaction_id": str(resp.id),
        }

    # ------- trailing-stop helpers --------------------------------------

    def list_open_trades(self):
        """Return open positions enriched with their bracket SL order info.

        Crypto positions report `stop_loss=None` (no bracket on Alpaca paper);
        trailing logic will skip them.
        """
        try:
            positions = self._trading.get_all_positions()
        except Exception as e:
            log.warning("alpaca_positions_failed", error=str(e))
            return []

        # Index any open stop orders by their parent symbol for stocks
        sl_by_symbol: Dict[str, Any] = {}
        try:
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.trading.requests import GetOrdersRequest
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=200)
            for o in self._trading.get_orders(filter=req) or []:
                otype = str(getattr(o, "order_type", "")).lower()
                if "stop" in otype:
                    sl_by_symbol[str(o.symbol)] = o
        except Exception as e:
            log.warning("alpaca_orders_lookup_failed", error=str(e))

        out = []
        for p in positions:
            symbol = str(p.symbol)
            qty = float(p.qty)
            avg_entry = float(p.avg_entry_price)
            side = "buy" if qty > 0 else "sell"
            sl_order = sl_by_symbol.get(symbol)
            sl_price = float(sl_order.stop_price) if (sl_order and getattr(sl_order, "stop_price", None)) else None
            out.append({
                "trade_id": symbol,  # We key by symbol on Alpaca (one position per symbol)
                "instrument": symbol,
                "side": side,
                "units": abs(qty),
                "entry": avg_entry,
                "stop_loss": sl_price,
                "stop_order_id": str(sl_order.id) if sl_order else None,
                "unrealized_pl": float(getattr(p, "unrealized_pl", 0) or 0),
            })
        return out

    def update_trade_stop(self, trade_id: str, new_stop_price: float) -> Dict[str, Any]:
        """Cancel the existing bracket SL child order and place a fresh stop order.

        `trade_id` here is the symbol (Alpaca model). Crypto symbols are no-ops
        because Alpaca paper doesn't support stop orders on crypto.
        """
        symbol = trade_id
        if _is_crypto(symbol):
            return {"status": "skipped", "reason": "crypto no SL support"}

        try:
            from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
            from alpaca.trading.requests import GetOrdersRequest, StopOrderRequest

            # Find existing SL for this symbol and cancel it
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=200, symbols=[symbol])
            for o in self._trading.get_orders(filter=req) or []:
                if "stop" in str(getattr(o, "order_type", "")).lower():
                    try:
                        self._trading.cancel_order_by_id(str(o.id))
                    except Exception as e:
                        log.warning("alpaca_cancel_sl_failed", order_id=str(o.id), error=str(e))

            # Determine the side of the protective stop (opposite of position)
            position = self._trading.get_open_position(symbol)
            pos_qty = float(position.qty)
            protect_side = OrderSide.SELL if pos_qty > 0 else OrderSide.BUY

            new_sl = StopOrderRequest(
                symbol=symbol,
                qty=abs(pos_qty),
                side=protect_side,
                time_in_force=TimeInForce.GTC,
                stop_price=str(round(new_stop_price, 2)),
            )
            resp = self._trading.submit_order(new_sl)
            log.info("alpaca_stop_updated", symbol=symbol, new_sl=new_stop_price, order_id=str(resp.id))
            return {"status": "ok", "trade_id": symbol, "new_stop": new_stop_price, "order_id": str(resp.id)}
        except Exception as e:
            log.error("alpaca_stop_update_failed", symbol=symbol, error=str(e))
            return {"status": "error", "reason": str(e)}
