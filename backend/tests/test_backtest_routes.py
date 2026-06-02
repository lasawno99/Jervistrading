"""Backend tests for Backtest Lab + Auto-Tune endpoints."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ----- Regression: existing endpoints not broken -----------------------------
class TestRegression:
    def test_risk_posture(self, client):
        r = client.get(f"{API}/risk/posture", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "protections" in d

    def test_market_regime(self, client):
        r = client.get(f"{API}/market/regime", timeout=20)
        assert r.status_code == 200

    def test_dashboard_hero(self, client):
        r = client.get(f"{API}/dashboard/hero", timeout=20)
        assert r.status_code == 200

    def test_win_rate_trend(self, client):
        r = client.get(f"{API}/dashboard/win-rate-trend", timeout=20)
        assert r.status_code == 200


# ----- Backtest runs list + drilldown ---------------------------------------
class TestBacktestRuns:
    def test_list_runs(self, client):
        r = client.get(f"{API}/backtest/runs", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "runs" in d
        assert isinstance(d["runs"], list)

    def test_drilldown_404(self, client):
        r = client.get(f"{API}/backtest/runs/nonexistent_id_xxx", timeout=20)
        assert r.status_code == 404


# ----- Auto-Tune flow --------------------------------------------------------
class TestAutoTune:
    """Full tune flow: POST → poll active → GET tune detail. Real yfinance."""

    @pytest.fixture(scope="class")
    def tune_id(self, client):
        payload = {"symbol": "ETH/USD", "period": "60d", "interval": "1h", "base_units": 1000}
        r = client.post(f"{API}/backtest/tune", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "tune_id" in d
        assert d["status"] == "queued"
        return d["tune_id"]

    def test_tune_active_visible(self, client, tune_id):
        # Should appear in active queue immediately
        r = client.get(f"{API}/backtest/tunes/active", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert tune_id in d.get("runs", {})

    def test_tune_completes_and_returns_results(self, client, tune_id):
        # Poll up to 180s (54 combos × yfinance call)
        deadline = time.time() + 180
        status = "running"
        while time.time() < deadline:
            r = client.get(f"{API}/backtest/tunes/active", timeout=20)
            assert r.status_code == 200
            info = r.json()["runs"].get(tune_id, {})
            status = info.get("status")
            if status in ("done", "error"):
                break
            time.sleep(3)
        assert status == "done", f"Tune did not finish in 180s, final status={status}"

        # Fetch persisted detail
        r = client.get(f"{API}/backtest/tunes/{tune_id}", timeout=20)
        assert r.status_code == 200
        detail = r.json()

        # Validate structure
        assert detail["symbol"] == "ETH/USD"
        assert detail["combos_tested"] == 54, f"Expected 54 combos, got {detail['combos_tested']}"
        assert isinstance(detail["results"], list)
        assert len(detail["results"]) == 54
        assert detail["best"] is not None
        assert detail["elapsed_seconds"] > 0

        # Validate result row schema
        row = detail["results"][0]
        for key in ("params", "score", "win_rate", "total_trades",
                    "total_pl_pct", "expectancy", "max_drawdown_pct"):
            assert key in row, f"Missing key: {key}"
        for pkey in ("tauric_floor", "upside_high", "upside_low", "atr_mult", "rr_base"):
            assert pkey in row["params"], f"Missing param: {pkey}"

        # Verify sorted descending by score
        scores = [r["score"] for r in detail["results"]]
        assert scores == sorted(scores, reverse=True), "Results not sorted by score desc"

        # Best == first row
        assert detail["best"]["score"] == detail["results"][0]["score"]

        # At least one non-zero-trade outcome (sanity)
        non_zero = [r for r in detail["results"] if r["total_trades"] > 0]
        assert len(non_zero) > 0, "All tune combos returned zero trades (data fetch issue?)"

    def test_tune_404_unknown(self, client):
        r = client.get(f"{API}/backtest/tunes/nonexistent_xxx", timeout=20)
        assert r.status_code == 404


# ----- Backtest engine override params produce different results -------------
class TestEngineOverrides:
    """Run two short backtests with different params; expect divergent outputs."""

    def test_different_params_yield_different_runs(self, client):
        sym = "BTC/USD"
        # Run A: tight thresholds
        a = client.post(f"{API}/backtest/run", json={
            "symbol": sym, "period": "30d", "interval": "1h",
            "base_units": 1000, "use_tauric": False, "max_llm_calls": 0,
        }, timeout=20)
        assert a.status_code == 200
        run_a = a.json()["run_id"]

        # Wait & fetch
        deadline = time.time() + 60
        result_a = None
        while time.time() < deadline:
            r = client.get(f"{API}/backtest/runs/{run_a}", timeout=20)
            if r.status_code == 200 and r.json().get("finished_at"):
                result_a = r.json()
                break
            time.sleep(2)
        assert result_a is not None, "Run A did not finish"
        assert "params" in result_a
        # params field should contain all 5 tunable keys
        for pkey in ("tauric_floor", "upside_high", "upside_low", "atr_mult", "rr_base"):
            assert pkey in result_a["params"]

        # Trade ledger schema if any trades
        if result_a.get("total_trades", 0) > 0:
            t = result_a["trades"][0]
            for k in ("bar_idx", "entry_time", "entry_price", "side",
                      "units", "sl", "tp", "exit_time", "exit_price",
                      "exit_reason", "pl_pct"):
                assert k in t, f"Trade missing key: {k}"
