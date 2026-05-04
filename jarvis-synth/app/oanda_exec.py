"""LAYER 5 — OANDA executor with Risk Guard.

Reuses guardrails.py (deterministic 8-rule checker, kill switch, daily-loss
limit) from forex-agent. Adds an R:R guardrail on top: TP distance must be at
least MIN_RR_RATIO times SL distance.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional

import structlog
from oandapyV20 import API
from oandapyV20.endpoints import accounts as v20_accounts
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


class OandaExecutor:
    def __init__(
        self,
        api_token: str,
        account_id: str,
        environment: str,
        guardrail_state: GuardrailState,
        min_rr_ratio: float,
        telegram_send: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        if environment.strip().lower() != "practice":
            raise RuntimeError(f"Refusing environment={environment!r}; practice only")
        self._client = API(access_token=api_token, environment="practice")
        if self._client.environment != "practice":
            raise RuntimeError(
                f"OANDA client resolved to non-practice env: {self._client.environment}"
            )
        self._account_id = account_id
        self._state = guardrail_state
        self._min_rr = min_rr_ratio
        self._telegram_send = telegram_send
        self._day_starting_balance: Optional[float] = None
        self._day_starting_balance_date: Optional[str] = None

    # Pricing helpers ---------------------------------------------------

    def get_price(self, instrument: str) -> Dict[str, Any]:
        req = v20_pricing.PricingInfo(
            accountID=self._account_id,
            params={"instruments": instrument},
        )
        resp = self._client.request(req)
        prices = resp.get("prices", [])
        if not prices:
            raise RuntimeError(f"No price for {instrument}")
        p = prices[0]
        return {
            "bid": float(p["bids"][0]["price"]),
            "ask": float(p["asks"][0]["price"]),
        }

    def get_account_summary(self) -> Dict[str, Any]:
        req = v20_accounts.AccountSummary(accountID=self._account_id)
        a = self._client.request(req).get("account", {})
        return {
            "balance": float(a.get("balance", 0) or 0),
            "nav": float(a.get("NAV", 0) or 0),
            "unrealized_pl": float(a.get("unrealizedPL", 0) or 0),
            "currency": a.get("currency"),
        }

    def list_positions(self):
        req = v20_positions.OpenPositions(accountID=self._account_id)
        resp = self._client.request(req)
        out = []
        for p in resp.get("positions", []):
            long_u = float(p.get("long", {}).get("units", 0) or 0)
            short_u = float(p.get("short", {}).get("units", 0) or 0)
            net = long_u + short_u
            out.append({
                "instrument": p.get("instrument"),
                "units": net,
                "side": "buy" if net > 0 else ("sell" if net < 0 else "flat"),
                "unrealized_pl": float(p.get("unrealizedPL", 0) or 0),
            })
        return out

    # Day-start balance bookkeeping ------------------------------------

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

    # Order placement --------------------------------------------------

    def execute(
        self,
        instrument: str,
        side: str,
        units: int,
        rationale: str = "",
        rr_ratio: float = 2.0,
        sl_pips: float = 10.0,
    ) -> Dict[str, Any]:
        """Place a market order with auto-derived SL and TP.

        - sl_pips: stop-loss distance in pips (or "price units" for non-FX like XAU)
        - rr_ratio: take-profit distance = sl_pips * rr_ratio
        Both must satisfy MIN_RR_RATIO via guardrail.
        """
        if side not in ("buy", "sell"):
            raise ValueError(f"side must be buy|sell (got {side!r})")
        if rr_ratio < self._min_rr:
            return {"status": "rejected", "reason": f"R:R {rr_ratio} < MIN_RR_RATIO {self._min_rr}"}

        px = self.get_price(instrument)
        ref = px["ask"] if side == "buy" else px["bid"]

        # Pip size: 0.0001 for FX, 0.01 for XAU/XAG (rough heuristic)
        pip = 0.01 if instrument.startswith("XAU") or instrument.startswith("XAG") else 0.0001
        sl_dist = sl_pips * pip
        tp_dist = sl_dist * rr_ratio

        if side == "buy":
            sl = round(ref - sl_dist, 5)
            tp = round(ref + tp_dist, 5)
            signed_units = units
        else:
            sl = round(ref + sl_dist, 5)
            tp = round(ref - tp_dist, 5)
            signed_units = -units

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
            check_order(order, self._state, self._account_state(), on_daily_halt=on_halt)
        except GuardrailRejection as e:
            log.warning("guardrail_rejected", instrument=instrument, reason=str(e))
            return {"status": "rejected", "reason": str(e)}

        body = {
            "order": {
                "instrument": instrument,
                "units": str(signed_units),
                "type": "MARKET",
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {"price": f"{sl:.5f}"},
                "takeProfitOnFill": {"price": f"{tp:.5f}"},
            }
        }
        try:
            resp = self._client.request(
                v20_orders.OrderCreate(accountID=self._account_id, data=body)
            )
        except Exception as e:
            log.error("order_failed", instrument=instrument, error=str(e))
            return {"status": "error", "reason": str(e)}

        fill = resp.get("orderFillTransaction") or {}
        log.info(
            "order_placed",
            instrument=instrument, side=side, units=units,
            sl=sl, tp=tp, fill_price=fill.get("price"),
        )
        return {
            "status": "filled" if fill else "submitted",
            "instrument": instrument, "side": side, "units": units,
            "stop_loss": sl, "take_profit": tp,
            "fill_price": fill.get("price"),
            "transaction_id": fill.get("id"),
        }
