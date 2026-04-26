"""Price-event trigger engine.

Watches a set of (instrument, condition, action) rules every N seconds.
When a rule fires, emits a JARVIS event: either notify, place order, or
launch a live strategy via the existing engine.

Conditions: 'above' / 'below' / 'crosses_above' / 'crosses_below'
Action types: 'notify' / 'market_order' / 'jarvis_prompt'

State persisted in Mongo `price_alerts` collection.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import oanda_client as oa

logger = logging.getLogger("price-triggers")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def create_alert(db, instrument: str, condition: str, level: float,
                       action: str = "notify",
                       order_units: Optional[int] = None,
                       order_stop_loss: Optional[float] = None,
                       jarvis_prompt: Optional[str] = None,
                       once: bool = True) -> dict:
    if condition not in ("above", "below", "crosses_above", "crosses_below"):
        return {"error": f"unsupported condition {condition}"}
    if action not in ("notify", "market_order", "jarvis_prompt"):
        return {"error": f"unsupported action {action}"}
    inst = oa._normalize_instrument(instrument)
    cur = oa.get_price(inst)
    last_mid = (cur["bid"] + cur["ask"]) / 2 if "bid" in cur else None
    alert = {
        "id": str(uuid.uuid4()),
        "instrument": inst,
        "condition": condition,
        "level": float(level),
        "action": action,
        "order_units": int(order_units) if order_units else None,
        "order_stop_loss": order_stop_loss,
        "jarvis_prompt": jarvis_prompt,
        "once": bool(once),
        "status": "active",
        "created_at": now_iso(),
        "last_price_seen": last_mid,
        "fired_at": None,
    }
    await db.price_alerts.insert_one(dict(alert))
    return {"ok": True, "alert": alert}


async def list_alerts(db, status: Optional[str] = None) -> list:
    q = {"status": status} if status else {}
    return await db.price_alerts.find(q, {"_id": 0}).sort("created_at", -1).to_list(100)


async def cancel_alert(db, alert_id: str) -> dict:
    r = await db.price_alerts.update_one({"id": alert_id}, {"$set": {"status": "cancelled"}})
    return {"ok": r.modified_count > 0}


def _condition_met(condition: str, level: float, last: Optional[float], cur: float) -> bool:
    if condition == "above":
        return cur > level
    if condition == "below":
        return cur < level
    if condition == "crosses_above":
        return last is not None and last <= level < cur
    if condition == "crosses_below":
        return last is not None and last >= level > cur
    return False


async def trigger_loop(db, jarvis_chat_fn, broadcast_fn=None, interval_sec: int = 8):
    """Polls price for active alerts, fires conditions, optionally executes orders."""
    logger.info("Price trigger loop started")
    while True:
        try:
            await asyncio.sleep(interval_sec)
            alerts = await db.price_alerts.find({"status": "active"}, {"_id": 0}).to_list(200)
            if not alerts:
                continue
            # Cache prices per instrument
            cache: dict = {}
            for a in alerts:
                inst = a["instrument"]
                if inst not in cache:
                    p = oa.get_price(inst)
                    if "bid" in p:
                        cache[inst] = (p["bid"] + p["ask"]) / 2
                if inst not in cache:
                    continue
                cur = cache[inst]
                last = a.get("last_price_seen")
                if _condition_met(a["condition"], a["level"], last, cur):
                    fired_msg = (
                        f"🔔 Alert fired: {inst} {a['condition']} {a['level']:.5f}  (now {cur:.5f})"
                    )
                    logger.info(fired_msg)

                    if a["action"] == "market_order":
                        units = a.get("order_units") or 1000
                        result = oa.place_market_order(inst, units, stop_loss=a.get("order_stop_loss"))
                        fired_msg += f"\n→ market order: {result}"
                    elif a["action"] == "jarvis_prompt" and a.get("jarvis_prompt"):
                        try:
                            reply, _ = await jarvis_chat_fn(db, [], a["jarvis_prompt"])
                            fired_msg += f"\n\n{reply[:500]}"
                        except Exception as e:
                            fired_msg += f"\n→ jarvis error: {e}"

                    if broadcast_fn:
                        try:
                            await broadcast_fn(fired_msg)
                        except Exception:
                            pass

                    update = {
                        "fired_at": now_iso(),
                        "fire_message": fired_msg,
                        "last_price_seen": cur,
                    }
                    if a.get("once"):
                        update["status"] = "fired"
                    await db.price_alerts.update_one({"id": a["id"]}, {"$set": update})
                else:
                    await db.price_alerts.update_one({"id": a["id"]}, {"$set": {"last_price_seen": cur}})
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("trigger loop error")
    logger.info("Price trigger loop stopped")
