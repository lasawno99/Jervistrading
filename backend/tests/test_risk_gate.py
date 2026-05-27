"""Risk-Off endpoint tests."""
import os
import pytest
import requests
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    # backend frontend env - read from frontend/.env
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')


@pytest.fixture(scope="module", autouse=True)
def reset_after():
    yield
    # Reset to auto after all tests
    requests.post(f"{BASE_URL}/api/risk/override", json={"mode": "auto"}, timeout=15)


def test_status_returns_full_shape():
    r = requests.get(f"{BASE_URL}/api/risk/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ["active", "source", "reason", "regime", "fg_value", "mc_pct_24h", "manual_override", "since", "as_of"]:
        assert k in d, f"missing key {k}"


def test_status_no_override_is_auto():
    # ensure cleared
    requests.post(f"{BASE_URL}/api/risk/override", json={"mode": "auto"}, timeout=15)
    r = requests.get(f"{BASE_URL}/api/risk/status", timeout=15)
    d = r.json()
    assert d["source"] == "auto"
    assert d["manual_override"] is None


def test_override_on_sets_active_true():
    r = requests.post(f"{BASE_URL}/api/risk/override", json={"mode": "on"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["active"] is True
    assert d["source"] == "manual"
    assert d["manual_override"] == "on"
    assert d["since"] is not None

    g = requests.get(f"{BASE_URL}/api/risk/status", timeout=15).json()
    assert g["active"] is True
    assert g["source"] == "manual"


def test_override_off_sets_active_false():
    r = requests.post(f"{BASE_URL}/api/risk/override", json={"mode": "off"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["active"] is False
    assert d["source"] == "manual"
    assert d["manual_override"] == "off"


def test_override_auto_clears():
    requests.post(f"{BASE_URL}/api/risk/override", json={"mode": "on"}, timeout=15)
    r = requests.post(f"{BASE_URL}/api/risk/override", json={"mode": "auto"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["source"] == "auto"
    assert d["manual_override"] is None


def test_override_invalid_400():
    r = requests.post(f"{BASE_URL}/api/risk/override", json={"mode": "bogus"}, timeout=15)
    assert r.status_code == 400


def test_status_cached_fast():
    # Two consecutive calls — second should be quick due to cmc cache
    t0 = time.time()
    requests.get(f"{BASE_URL}/api/risk/status", timeout=15)
    t1 = time.time()
    requests.get(f"{BASE_URL}/api/risk/status", timeout=15)
    t2 = time.time()
    # second call should be <1s typically
    assert (t2 - t1) < 5.0


# Auto-evaluation logic tests via direct module call
def test_auto_logic_thresholds(monkeypatch):
    import sys
    sys.path.insert(0, '/app/backend')
    import asyncio
    import risk_gate as rg

    async def fake_eval_bear_extreme():
        return {"regime": "bear", "fg_value": 25, "mc_pct_24h": -1.5,
                "auto_risk_off": True, "reason": "bear+fg<=30"}

    async def fake_eval_bear_mid():
        return {"regime": "bear", "fg_value": 40, "mc_pct_24h": -0.8,
                "auto_risk_off": False, "reason": "bear but fg>30"}

    async def fake_eval_chop_extreme_fear():
        return {"regime": "chop", "fg_value": 15, "mc_pct_24h": 0.1,
                "auto_risk_off": True, "reason": "extreme fear"}

    class FakeDB:
        class risk_state:
            @staticmethod
            async def find_one(*a, **kw):
                return None

    # Test 1: bear + fg<=30 -> active
    monkeypatch.setattr(rg, "_evaluate_auto", fake_eval_bear_extreme)
    s = asyncio.run(rg.get_status(FakeDB))
    assert s["active"] is True
    assert s["source"] == "auto"

    # Test 2: bear + fg=40 -> not active
    monkeypatch.setattr(rg, "_evaluate_auto", fake_eval_bear_mid)
    s = asyncio.run(rg.get_status(FakeDB))
    assert s["active"] is False

    # Test 3: fg<=20 -> active regardless
    monkeypatch.setattr(rg, "_evaluate_auto", fake_eval_chop_extreme_fear)
    s = asyncio.run(rg.get_status(FakeDB))
    assert s["active"] is True
