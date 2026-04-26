"""Schedule + reminder loop. Runs in background, fires due jarvis tasks."""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

try:
    from croniter import croniter
except Exception:
    croniter = None  # type: ignore

logger = logging.getLogger("scheduler")


def validate_cron(expr: str) -> bool:
    if not croniter:
        return False
    try:
        croniter(expr, datetime.now(timezone.utc))
        return True
    except Exception:
        return False


def compute_next_run(cron: Optional[str], at: Optional[str]) -> Optional[str]:
    now = datetime.now(timezone.utc)
    if cron and croniter:
        try:
            it = croniter(cron, now)
            return it.get_next(datetime).astimezone(timezone.utc).isoformat()
        except Exception:
            return None
    if at:
        return at
    return None


async def scheduler_loop(db, jarvis_chat_fn, broadcast_fn=None, interval_sec: int = 30):
    """
    Polls schedules every interval_sec. For any whose `next_run` <= now and status==active:
    - Run the prompt through JARVIS (no tg chat context — agent has full tools).
    - Save the result to `notifications` collection.
    - Broadcast to all telegram subscribers (if broadcast_fn provided).
    - Mark schedule's last_run, compute next_run for cron schedules; deactivate one-shots.
    """
    logger.info("Scheduler loop started")
    while True:
        try:
            await asyncio.sleep(interval_sec)
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor = db.schedules.find({"status": "active", "next_run": {"$lte": now_iso}}, {"_id": 0})
            due = await cursor.to_list(50)
            for s in due:
                logger.info(f"Firing schedule {s['id']}: {s['title']}")
                try:
                    reply, _ = await jarvis_chat_fn(db, [], s["prompt"])
                except Exception as e:
                    logger.exception("scheduler jarvis failed")
                    reply = f"(scheduler error: {e})"

                note = {
                    "id": s["id"] + ":" + now_iso,
                    "schedule_id": s["id"],
                    "title": s["title"],
                    "content": reply,
                    "ts": now_iso,
                    "read": False,
                }
                await db.notifications.insert_one(dict(note))

                if broadcast_fn:
                    try:
                        await broadcast_fn(f"🔔 <b>{s['title']}</b>\n{reply[:3500]}")
                    except Exception:
                        pass

                # Update schedule
                next_run = compute_next_run(s.get("cron"), None) if s.get("cron") else None
                update = {"$set": {"last_run": now_iso}}
                if next_run:
                    update["$set"]["next_run"] = next_run
                else:
                    update["$set"]["status"] = "completed"
                await db.schedules.update_one({"id": s["id"]}, update)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.exception(f"scheduler tick error: {e}")
    logger.info("Scheduler loop stopped")
