"""OANDA practice-account tool: market data + paper order placement.

Hard-locked to the practice environment (`api-fxpractice.oanda.com`).
Any attempt to instantiate against `live` raises immediately.

Order placement flows through `app.guardrails.check_order`. The LLM never
bypasses guardrails — they are called inside `place_paper_order` itself.

Daily P&L bookkeeping is lazy: on the first order of each new UTC day the
day's starting balance is captured from the live OANDA account NAV.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog
from oandapyV20 import API
from oandapyV20.endpoints import accounts as v20_accounts
from oandapyV20.endpoints import instruments as v20_instruments
from oandapyV20.endpoints import orders as v20_orders
from oandapyV20.endpoints import positions as v20_positions
from oandapyV20.endpoints import pricing as v20_pricing

from app.guardrails import (
    AccountState,
    GuardrailRejection,
    GuardrailState,
    Order,
    check_order,
    fire_telegram_alert,
)

log = structlog.get_logger()

PRACTICE_HOSTNAME = "api-fxpractice.oanda.com"


class OandaTool:
    """Thin wrapper over oandapyV20, locked to the practice environment."""

    def __init__(
        self,
        api_token: str,
        account_id: str,
        environment: str,
        guardrail_state: GuardrailState,
        telegram_send: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        if environment.strip().lower() != "practice":
            raise RuntimeError(
                f"OandaTool refuses environment={environment!r}; practice only"
            )
        self._client = API(access_token=api_token, environment="practice")
        # Sanity-check we resolved to the practice environment.
        if self._client.environment != "practice":
            raise RuntimeError(
                f"OANDA client resolved to non-practice environment: {self._client.environment}"
            )
        self._account_id = account_id
        self._state = guardrail_state
        self._telegram_send = telegram_send
        self._day_starting_balance: Optional[float] = None
        self._day_starting_balance_date: Optional[str] = None

    # --- market data ---------------------------------------------------

    def get_price(self, instrument: str) -> Dict[str, Any]:
        req = v20_pricing.PricingInfo(
            accountID=self._account_id,
            params={"instruments": instrument},
        )
        resp = self._client.request(req)
        prices = resp.get("prices", [])
        if not prices:
            raise RuntimeError(f"No price returned for {instrument}")
        p = prices[0]
        return {
            "instrument": p.get("instrument", instrument),
            "bid": float(p["bids"][0]["price"]),
            "ask": float(p["asks"][0]["price"]),
            "time": p.get("time"),
        }

    def get_candles(
        self, instrument: str, granularity: str = "M15", count: int = 50
    ) -> List[Dict[str, Any]]:
        count = max(1, min(int(count), 200))
        req = v20_instruments.InstrumentsCandles(
            instrument=instrument,
            params={
                "granularity": granularity,
                "count": count,
                "price": "M",
            },
        )
        resp = self._client.request(req)
        out: List[Dict[str, Any]] = []
        for c in resp.get("candles", []):
            if not c.get("complete", False):
                continue
            mid = c.get("mid", {})
            out.append(
                {
                    "time": c.get("time"),
                    "open": float(mid.get("o", 0.0)),
                    "high": float(mid.get("h", 0.0)),
                    "low": float(mid.get("l", 0.0)),
                    "close": float(mid.get("c", 0.0)),
                    "volume": int(c.get("volume", 0)),
                }
            )
        return out

    # --- account / positions -------------------------------------------

    def list_positions(self) -> List[Dict[str, Any]]:
        req = v20_positions.OpenPositions(accountID=self._account_id)
        resp = self._client.request(req)
        out: List[Dict[str, Any]] = []
        for p in resp.get("positions", []):
            long_units = float(p.get("long", {}).get("units", 0) or 0)
            short_units = float(p.get("short", {}).get("units", 0) or 0)
            net = long_units + short_units
            unrealized = float(p.get("unrealizedPL", 0) or 0)
            out.append(
                {
                    "instrument": p.get("instrument"),
                    "units": net,
                    "side": "buy" if net > 0 else ("sell" if net < 0 else "flat"),
                    "unrealized_pl": unrealized,
                }
            )
        return out

    def close_position(self, instrument: str, side: str = "all") -> Dict[str, Any]:
        """Close an open position to lock in profit/loss.

        side ∈ {"long", "short", "all"}. "all" closes whichever side is open.
        """
        if side not in ("long", "short", "all"):
            raise ValueError(f"side must be long|short|all (got {side!r})")

        body: Dict[str, Any] = {}
        if side in ("long", "all"):
            body["longUnits"] = "ALL"
        if side in ("short", "all"):
            body["shortUnits"] = "ALL"

        req = v20_positions.PositionClose(
            accountID=self._account_id, instrument=instrument, data=body
        )
        try:
            resp = self._client.request(req)
        except Exception as e:
            log.warning("close_position_failed", instrument=instrument, error=str(e))
            return {"status": "error", "reason": str(e)}

        long_fill = resp.get("longOrderFillTransaction") or {}
        short_fill = resp.get("shortOrderFillTransaction") or {}
        realized = float(long_fill.get("pl", 0) or 0) + float(short_fill.get("pl", 0) or 0)
        log.info(
            "position_closed",
            instrument=instrument,
            side=side,
            realized_pl=realized,
        )
        return {
            "status": "closed",
            "instrument": instrument,
            "side": side,
            "realized_pl": realized,
            "long_fill_id": long_fill.get("id"),
            "short_fill_id": short_fill.get("id"),
        }

    def get_account_summary(self) -> Dict[str, Any]:
        req = v20_accounts.AccountSummary(accountID=self._account_id)
        resp = self._client.request(req)
        a = resp.get("account", {})
        return {
            "balance": float(a.get("balance", 0) or 0),
            "nav": float(a.get("NAV", 0) or 0),
            "unrealized_pl": float(a.get("unrealizedPL", 0) or 0),
            "currency": a.get("currency"),
        }

    def _ensure_day_starting_balance(self) -> float:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._day_starting_balance_date != today:
            summary = self.get_account_summary()
            self._day_starting_balance = float(summary["nav"])
            self._day_starting_balance_date = today
            log.info(
                "day_starting_balance_set",
                date=today,
                balance=self._day_starting_balance,
            )
        return float(self._day_starting_balance or 0.0)

    def _build_account_state(self) -> AccountState:
        starting = self._ensure_day_starting_balance()
        summary = self.get_account_summary()
        # realized today = current NAV - starting NAV - current unrealized
        unrealized = summary["unrealized_pl"]
        realized = summary["nav"] - starting - unrealized
        return AccountState(
            starting_balance=starting,
            realized_pl=realized,
            unrealized_pl=unrealized,
        )

    # --- order placement -----------------------------------------------

    def place_paper_order(
        self,
        *,
        instrument: str,
        side: str,
        units: int,
        stop_loss: float,
        take_profit: float,
        rationale: str = "",
    ) -> Dict[str, Any]:
        """Validate via guardrails, then submit a market order to OANDA practice."""
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell' (got {side!r})")
        signed_units = int(units) if side == "buy" else -int(units)

        order = Order(
            instrument=instrument,
            side=side,
            units=int(units),
            stop_loss=stop_loss,
            take_profit=take_profit,
            rationale=rationale,
        )

        account_state = self._build_account_state()
        on_halt = (
            fire_telegram_alert(self._telegram_send) if self._telegram_send else None
        )
        try:
            check_order(order, self._state, account_state, on_daily_halt=on_halt)
        except GuardrailRejection as e:
            log.warning("guardrail_rejected", reason=str(e), instrument=instrument)
            return {"status": "rejected", "reason": str(e)}

        body = {
            "order": {
                "instrument": instrument,
                "units": str(signed_units),
                "type": "MARKET",
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {"price": f"{stop_loss:.5f}"},
                "takeProfitOnFill": {"price": f"{take_profit:.5f}"},
            }
        }
        req = v20_orders.OrderCreate(accountID=self._account_id, data=body)
        resp = self._client.request(req)
        fill = resp.get("orderFillTransaction") or {}
        log.info(
            "order_placed",
            instrument=instrument,
            side=side,
            units=units,
            stop_loss=stop_loss,
            take_profit=take_profit,
            fill_price=fill.get("price"),
            transaction_id=fill.get("id"),
        )
        return {
            "status": "filled" if fill else "submitted",
            "instrument": instrument,
            "side": side,
            "units": units,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "fill_price": fill.get("price"),
            "transaction_id": fill.get("id"),
            "rationale": rationale,
        }
