#!/usr/bin/env python3
"""
jarvis-cli — talk to your JARVIS backend from any terminal.

Install (one line):
  curl -fsSL https://jarvis-agent-16.preview.emergentagent.com/api/cli/jarvis -o ~/.local/bin/jarvis && chmod +x ~/.local/bin/jarvis

Set your backend URL once (or it falls back to the public preview):
  export JARVIS_URL=https://jarvis-agent-16.preview.emergentagent.com

Usage:
  jarvis "what's my day look like"
  jarvis "buy 0.05 BTC and remind me to check at 4pm"
  jarvis status
  jarvis schedules
  jarvis todos
  jarvis inbox
  jarvis reset                # clears CLI session (memory persists server-side)
  jarvis --help

No keys needed locally. JARVIS uses the keys you set on the server.
"""

from __future__ import annotations
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://jarvis-agent-16.preview.emergentagent.com"
CONFIG_DIR = Path(os.environ.get("JARVIS_HOME", str(Path.home() / ".jarvis")))
CONFIG_FILE = CONFIG_DIR / "config.json"


# ---------- ANSI colors ----------
def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


C = {
    "cyan":  "\033[36m",
    "mag":   "\033[35m",
    "amber": "\033[33m",
    "green": "\033[32m",
    "red":   "\033[31m",
    "dim":   "\033[2m",
    "bold":  "\033[1m",
    "off":   "\033[0m",
}
if not supports_color():
    C = {k: "" for k in C}


def color(s: str, c: str) -> str:
    return f"{C.get(c, '')}{s}{C['off']}"


# ---------- Config ----------
def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def base_url() -> str:
    return os.environ.get("JARVIS_URL", DEFAULT_URL).rstrip("/")


# ---------- HTTP ----------
def http(method: str, path: str, payload: dict | None = None, timeout: int = 60) -> dict:
    url = f"{base_url()}/api{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "jarvis-cli/1.0 (+https://emergent.sh)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return {"_error": json.loads(e.read().decode())}
        except Exception:
            return {"_error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"_error": str(e)}


# ---------- Banner ----------
BANNER = r"""
   ___  ___  ____ _   _ ___ ___
  |_  |/ _ \|  _ \ | | | _ \_ _|
   _| | (_) | |_) | |/ /  _/| |
  |__/ \___/|  __/|_|_/|_| |___|
            |_|     // CLI ▸ neural link
""".strip("\n")


def cmd_status() -> int:
    s = http("GET", "/jarvis/status")
    info = http("GET", "/")
    risk = http("GET", "/bot/risk")
    eq = http("GET", "/bot/positions")
    fx = http("GET", "/forex/status")

    print(color(BANNER, "cyan"))
    print()
    print(color("// CONNECTED ▸ ", "dim") + color(base_url(), "cyan"))
    print()
    print(color("Brain   ", "dim"), end="")
    print(color("● online" if s.get("configured") else "○ offline (no ANTHROPIC_API_KEY)",
                "green" if s.get("configured") else "amber"),
          color(f"  {s.get('model','?')}  ·  {s.get('tool_count','?')} tools", "dim"))
    print(color("Kimi    ", "dim"), end="")
    print(color("● live" if info.get("kimi_active") else "○ fallback", "green" if info.get("kimi_active") else "amber"),
          color(f"  {info.get('model','?')}", "dim"))
    print(color("Telegram", "dim"), end="")
    print(color("● linked" if info.get("telegram_configured") else "○ no token",
                "green" if info.get("telegram_configured") else "red"))
    print(color("Forex   ", "dim"), end="")
    print(color("● connected" if fx.get("oanda_configured") else "○ mock",
                "green" if fx.get("oanda_configured") else "amber"),
          color(f"  ({fx.get('env','-')})", "dim"))
    print()
    print(color("Account ", "dim") + color(f"${eq.get('equity', 0):,.2f}", "bold"),
          color(f"  cash ${eq.get('cash', 0):,.2f}  ·  P/L {eq.get('total_pl_pct', 0):+.2f}%", "dim"))
    print(color("Risk    ", "dim") + color("KILL ON" if risk.get("kill_switch") else "armed",
                "red" if risk.get("kill_switch") else "green"),
          color(f"  max pos ${risk.get('max_position_notional', 0):,.0f}  ·  max loss ${risk.get('max_daily_loss', 0):,.0f}", "dim"))
    return 0


def cmd_chat(msg: str) -> int:
    cfg = load_config()
    sid = cfg.get("session_id") or "cli-default"
    print(color("jarvis", "cyan") + color(" ▸ thinking ", "dim") + color("●", "amber") + " ", end="", flush=True)
    t0 = time.time()
    r = http("POST", "/jarvis/chat", {"message": msg, "session_id": sid, "user_name": cfg.get("name", "Operator")})
    dt = time.time() - t0
    sys.stdout.write("\r" + " " * 40 + "\r")
    if "_error" in r:
        print(color("✗ error: ", "red") + str(r["_error"]))
        return 1
    cfg["session_id"] = r.get("session_id", sid)
    save_config(cfg)
    print(color("jarvis ▸", "cyan") + color(f" ({dt:.1f}s)", "dim"))
    print(color(r.get("reply", "(empty)"), "bold"))
    return 0


def cmd_schedules() -> int:
    r = http("GET", "/jarvis/schedules")
    items = r.get("schedules", [])
    if not items:
        print(color("// no active schedules", "dim"))
        return 0
    for s in items:
        when = s.get("cron") or s.get("at") or "?"
        nxt = s.get("next_run", "")
        print(f"{color('●', 'cyan')} {color(s['title'], 'bold')}")
        print(f"  {color('when', 'dim')}  {when}")
        print(f"  {color('next', 'dim')}  {nxt}")
        print(f"  {color('do  ', 'dim')}  {s['prompt']}")
        print()
    return 0


def cmd_todos() -> int:
    r = http("GET", "/jarvis/todos")
    items = r.get("todos", [])
    if not items:
        print(color("// no open todos", "dim"))
        return 0
    for t in items:
        print(f"{color('☐', 'amber')} {t['text']}  {color(t['id'][:8], 'dim')}")
    return 0


def cmd_inbox() -> int:
    r = http("GET", "/jarvis/notifications?limit=10")
    items = r.get("notifications", [])
    if not items:
        print(color("// inbox empty", "dim"))
        return 0
    for n in items:
        print(f"{color('🔔', 'amber')} {color(n['title'], 'bold')}  {color(n.get('ts',''), 'dim')}")
        print(f"  {n['content']}")
        print()
    return 0


def cmd_reset() -> int:
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
    print(color("✓ local CLI session cleared. (server-side memory preserved)", "green"))
    return 0


def usage() -> None:
    print(__doc__)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return cmd_status()
    cmd = argv[1].lower()
    if cmd in ("-h", "--help", "help"):
        usage()
        return 0
    if cmd == "status":
        return cmd_status()
    if cmd in ("schedules", "schedule"):
        return cmd_schedules()
    if cmd in ("todos", "todo"):
        return cmd_todos()
    if cmd in ("inbox", "notif", "notifications"):
        return cmd_inbox()
    if cmd == "reset":
        return cmd_reset()
    # Anything else is treated as a chat message
    msg = " ".join(argv[1:])
    return cmd_chat(msg)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        print()
        sys.exit(130)
