"""Backend test suite for Jarvis Trading Bot API.

Covers:
- Service info / config flags
- Chat + tasks
- Mock feeds (trading, twitter, calendar, news)
- Bot status, positions, trade execution, signals, auto-mode, reset
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to reading frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session", autouse=True)
def _reset_state(client):
    # Reset before suite for deterministic state
    r = client.post(f"{API}/bot/reset", timeout=15)
    assert r.status_code == 200, f"reset failed: {r.status_code} {r.text}"
    yield


# ---------------- Service info ----------------

class TestServiceInfo:
    def test_root_service_info(self, client):
        r = client.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["service"] == "jarvis"
        assert d["kimi_active"] is False
        assert d["telegram_configured"] is False
        assert "model" in d


# ---------------- Chat + Tasks ----------------

class TestChatAndTasks:
    def test_chat_trading_intent_creates_task(self, client):
        r = client.post(f"{API}/chat", json={"message": "buy 0.1 btc"}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["intent"] == "trading"
        assert d["reply"] and isinstance(d["reply"], str)
        assert d["session_id"]
        assert d["spawned_task"] is not None
        assert d["spawned_task"]["panel"] == "trading"
        assert d["spawned_task"]["status"] == "running"

    def test_tasks_listing_after_chat(self, client):
        r = client.get(f"{API}/tasks", timeout=15)
        assert r.status_code == 200
        tasks = r.json()
        assert isinstance(tasks, list)
        assert len(tasks) >= 1
        # No mongo _id leakage
        for t in tasks:
            assert "_id" not in t
            assert "id" in t and "title" in t and "panel" in t


# ---------------- Mock feeds ----------------

class TestFeeds:
    def test_trading_feed_six_tickers(self, client):
        r = client.get(f"{API}/feed/trading", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        symbols = {row["symbol"] for row in rows}
        assert symbols == {"BTC", "ETH", "OIL", "GOLD", "TSLA", "NVDA"}
        for row in rows:
            assert isinstance(row["price"], (int, float))
            assert isinstance(row["change"], (int, float))
            assert row["posture"]

    def test_trading_feed_random_walk(self, client):
        r1 = client.get(f"{API}/feed/trading", timeout=15).json()
        time.sleep(0.2)
        r2 = client.get(f"{API}/feed/trading", timeout=15).json()
        prices1 = {r["symbol"]: r["price"] for r in r1}
        prices2 = {r["symbol"]: r["price"] for r in r2}
        # At least one symbol price should change between consecutive ticks
        diffs = sum(1 for s in prices1 if prices1[s] != prices2[s])
        assert diffs >= 1, f"prices identical across calls: {prices1} vs {prices2}"

    def test_twitter_feed(self, client):
        r = client.get(f"{API}/feed/twitter", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) >= 1
        assert {"id", "handle", "name", "content", "timestamp", "likes"} <= set(items[0].keys())

    def test_calendar_feed(self, client):
        r = client.get(f"{API}/feed/calendar", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) >= 1
        assert {"id", "title", "time", "attendees"} <= set(items[0].keys())

    def test_news_feed(self, client):
        r = client.get(f"{API}/feed/news", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) >= 1
        assert {"id", "headline", "source", "timestamp"} <= set(items[0].keys())


# ---------------- Bot status / positions ----------------

class TestBotStatus:
    def test_bot_status(self, client):
        r = client.get(f"{API}/bot/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["kimi_active"] is False
        assert "telegram" in d
        assert d["telegram"]["configured"] is False
        acc = d["account"]
        assert acc["starting_cash"] == 100_000.0
        assert acc["cash"] == 100_000.0
        assert acc["equity"] == 100_000.0
        assert acc["positions"] == []

    def test_bot_positions_initial(self, client):
        r = client.get(f"{API}/bot/positions", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["cash"] == 100_000.0
        assert d["positions"] == []


# ---------------- Trade execution ----------------

class TestTrade:
    def test_buy_btc_then_position_reflects(self, client):
        r = client.post(f"{API}/bot/trade", json={"symbol": "BTC", "side": "buy", "qty": 0.1}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        trade = d["trade"]
        assert trade["symbol"] == "BTC"
        assert trade["side"] == "buy"
        assert trade["qty"] == 0.1
        assert trade["price"] > 0

        # Verify positions reflect the buy
        r2 = client.get(f"{API}/bot/positions", timeout=15)
        assert r2.status_code == 200
        eq = r2.json()
        positions = eq["positions"]
        btc = [p for p in positions if p["symbol"] == "BTC"]
        assert len(btc) == 1
        p = btc[0]
        assert p["qty"] == 0.1
        assert "current_price" in p and "market_value" in p
        assert "pl" in p and "pl_pct" in p
        # Cash should have decreased
        assert eq["cash"] < 100_000.0

    def test_trade_invalid_symbol_returns_400(self, client):
        r = client.post(f"{API}/bot/trade", json={"symbol": "DOGE", "side": "buy", "qty": 1}, timeout=15)
        assert r.status_code == 400
        assert "Unknown symbol" in r.text or "detail" in r.json()

    def test_trade_insufficient_cash_returns_400(self, client):
        r = client.post(f"{API}/bot/trade", json={"symbol": "BTC", "side": "buy", "qty": 1000}, timeout=15)
        assert r.status_code == 400
        assert "Insufficient" in r.text or "detail" in r.json()


# ---------------- Signals ----------------

class TestSignals:
    def test_generate_signal_eventually(self, client):
        last = None
        for _ in range(10):
            r = client.post(f"{API}/bot/signal", timeout=20)
            assert r.status_code == 200
            last = r.json()
            if isinstance(last, dict) and last.get("id"):
                break
        assert last is not None
        # Either we got an actionable signal, or "no edge" response
        if last.get("id"):
            assert last["status"] == "pending"
            assert last["action"] in ("BUY", "SELL")
            assert last["symbol"]
            assert "_id" not in last
        else:
            assert last.get("ok") is False
            assert last.get("reason") == "no edge"

    def test_signals_listing(self, client):
        r = client.get(f"{API}/bot/signals", timeout=15)
        assert r.status_code == 200
        sigs = r.json()
        assert isinstance(sigs, list)
        for s in sigs:
            assert "_id" not in s

    def _get_pending_signal(self, client):
        for _ in range(15):
            r = client.post(f"{API}/bot/signal", timeout=20)
            d = r.json()
            if isinstance(d, dict) and d.get("id"):
                return d
        return None

    def test_approve_signal_executes(self, client):
        sig = self._get_pending_signal(client)
        if not sig:
            pytest.skip("Could not obtain a pending signal after multiple attempts")
        r = client.post(f"{API}/bot/signal/{sig['id']}/approve", timeout=15)
        assert r.status_code == 200, r.text
        # Verify signal status is now executed (or failed if e.g. insufficient cash for SELL)
        sigs = client.get(f"{API}/bot/signals", timeout=15).json()
        match = [s for s in sigs if s["id"] == sig["id"]]
        assert match
        assert match[0]["status"] in ("executed", "failed")

    def test_skip_signal(self, client):
        sig = self._get_pending_signal(client)
        if not sig:
            pytest.skip("Could not obtain pending signal")
        r = client.post(f"{API}/bot/signal/{sig['id']}/skip", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        sigs = client.get(f"{API}/bot/signals", timeout=15).json()
        match = [s for s in sigs if s["id"] == sig["id"]]
        assert match and match[0]["status"] == "skipped"


# ---------------- Auto-mode + reset ----------------

class TestAutoAndReset:
    def test_auto_mode_toggle(self, client):
        r1 = client.post(f"{API}/bot/auto", json={"on": True}, timeout=15)
        assert r1.status_code == 200
        assert r1.json() == {"auto": True}
        r2 = client.post(f"{API}/bot/auto", json={"on": False}, timeout=15)
        assert r2.status_code == 200
        assert r2.json() == {"auto": False}

    def test_reset_clears_state(self, client):
        # Make a trade so there is state to reset
        client.post(f"{API}/bot/trade", json={"symbol": "ETH", "side": "buy", "qty": 0.5}, timeout=15)
        r = client.post(f"{API}/bot/reset", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        eq = client.get(f"{API}/bot/positions", timeout=15).json()
        assert eq["cash"] == 100_000.0
        assert eq["positions"] == []
        sigs = client.get(f"{API}/bot/signals", timeout=15).json()
        assert sigs == []
