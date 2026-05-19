"""Tests for /api/market/* (CoinMarketCap-backed) endpoints.

Validates:
- /status shape and configured=true
- /fear-greed shape with realistic 0-100 value
- /regime shape with bull/bear/chop and global metrics
- /top-movers shape with 5 gainers/losers
- 75s in-memory cache prevents calls_today increment on consecutive hits
- CMC_API_KEY is never leaked in any response body
"""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass
API = f"{BASE_URL}/api"

# Pull the actual key fragment from backend .env to check leakage
CMC_KEY = ""
try:
    with open("/app/backend/.env") as f:
        for line in f:
            if line.startswith("CMC_API_KEY="):
                CMC_KEY = line.split("=", 1)[1].strip()
                break
except Exception:
    pass


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


def _no_key_leak(text: str):
    assert "CMC_API_KEY" not in text, "Response leaks 'CMC_API_KEY' literal"
    if CMC_KEY:
        assert CMC_KEY not in text, "Response leaks actual CMC API key value"
        # Also fragment-check (first 12 chars)
        assert CMC_KEY[:12] not in text, "Response leaks CMC API key fragment"


class TestMarketStatus:
    def test_status_shape(self, client):
        r = client.get(f"{API}/market/status", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("configured", "cache_entries", "calls_today", "cache_ttl_seconds"):
            assert k in d, f"missing {k} in {d}"
        assert d["configured"] is True
        assert d["cache_ttl_seconds"] == 75
        assert isinstance(d["cache_entries"], int)
        assert isinstance(d["calls_today"], int)
        _no_key_leak(r.text)


class TestFearGreed:
    def test_fear_greed_shape(self, client):
        r = client.get(f"{API}/market/fear-greed", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("value"), int)
        assert 0 <= d["value"] <= 100
        assert isinstance(d.get("classification"), str) and d["classification"]
        assert isinstance(d.get("fetched_at"), (int, float))
        _no_key_leak(r.text)


class TestRegime:
    def test_regime_shape(self, client):
        r = client.get(f"{API}/market/regime", timeout=25)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["regime"] in ("bull", "bear", "chop"), f"unexpected regime {d['regime']}"
        assert isinstance(d["btc_dominance"], (int, float)) and d["btc_dominance"] > 0
        assert isinstance(d["total_market_cap_usd"], (int, float)) and d["total_market_cap_usd"] > 0
        assert isinstance(d["total_volume_24h_usd"], (int, float)) and d["total_volume_24h_usd"] > 0
        assert "fetched_at" in d
        _no_key_leak(r.text)


class TestTopMovers:
    def test_top_movers_shape(self, client):
        r = client.get(f"{API}/market/top-movers", timeout=25)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d["gainers"], list) and len(d["gainers"]) == 5
        assert isinstance(d["losers"], list) and len(d["losers"]) == 5
        for item in d["gainers"] + d["losers"]:
            assert "symbol" in item and item["symbol"]
            assert "name" in item and item["name"]
            assert isinstance(item["price"], (int, float))
            assert isinstance(item["change_24h"], (int, float))
        # Gainers should be ordered by descending change_24h
        gainers_changes = [g["change_24h"] for g in d["gainers"]]
        assert gainers_changes == sorted(gainers_changes, reverse=True)
        losers_changes = [l_["change_24h"] for l_ in d["losers"]]
        assert losers_changes == sorted(losers_changes)
        # Gainers top should be > losers top
        assert d["gainers"][0]["change_24h"] > d["losers"][0]["change_24h"]
        _no_key_leak(r.text)


class TestCaching:
    """Verify 75s in-memory cache prevents duplicate upstream calls."""

    def test_repeated_calls_dont_bump_counter(self, client):
        # Prime the cache for all 3 endpoints
        client.get(f"{API}/market/fear-greed", timeout=20)
        client.get(f"{API}/market/regime", timeout=25)
        client.get(f"{API}/market/top-movers", timeout=25)
        time.sleep(0.5)

        s1 = client.get(f"{API}/market/status", timeout=15).json()
        before = s1["calls_today"]

        # Hit each endpoint twice in quick succession (well within 75s TTL)
        for _ in range(2):
            assert client.get(f"{API}/market/fear-greed", timeout=20).status_code == 200
            assert client.get(f"{API}/market/regime", timeout=25).status_code == 200
            assert client.get(f"{API}/market/top-movers", timeout=25).status_code == 200

        s2 = client.get(f"{API}/market/status", timeout=15).json()
        after = s2["calls_today"]

        # Cache should have prevented any new upstream calls
        assert after == before, (
            f"calls_today incremented from {before} -> {after}; cache not working"
        )
        # cache_entries should be >= 3 (top-movers, regime, fear-greed, global-metrics)
        assert s2["cache_entries"] >= 3


class TestKeyLeakage:
    """Ensure CMC_API_KEY never appears in any /api response body."""

    def test_no_key_in_market_endpoints(self, client):
        for path in ("/market/status", "/market/fear-greed", "/market/regime", "/market/top-movers"):
            r = client.get(f"{API}{path}", timeout=25)
            assert r.status_code == 200, f"{path}: {r.status_code}"
            _no_key_leak(r.text)
            # also check headers don't carry the key
            for k, v in r.headers.items():
                assert "CMC" not in k.upper() or "API_KEY" not in k.upper()
                if CMC_KEY:
                    assert CMC_KEY not in v
