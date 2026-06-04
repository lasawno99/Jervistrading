"""Regression tests for /api/scaling/* — the 5→10 instrument readiness gate.

Uses FastAPI TestClient + a mocked Mongo collection (since the readiness gate
only touches `closed_trades.count_documents` and `scaling_state.replace_one/find_one`,
we can fake those with a small async stub).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scaling_routes  # noqa: E402


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class FakeColl:
    def __init__(self, trades_total=0, trades_wins=0, scaling_doc=None):
        self.trades_total = trades_total
        self.trades_wins = trades_wins
        self.scaling_doc = scaling_doc
        self.replaced = None

    # closed_trades.count_documents
    async def count_documents(self, query: Dict[str, Any]):
        if query == {}:
            return self.trades_total
        if "pl_pct" in query:
            return self.trades_wins
        return 0

    # scaling_state.find_one
    async def find_one(self, query, projection=None):
        if self.scaling_doc and query.get("_id") == "jarvis-synth":
            return dict(self.scaling_doc)
        return None

    # scaling_state.replace_one
    async def replace_one(self, query, doc, upsert=False):
        self.replaced = doc


class FakeDB:
    def __init__(self, total=0, wins=0, scaling_doc=None):
        self.closed_trades = FakeColl(trades_total=total, trades_wins=wins)
        self.scaling_state = FakeColl(scaling_doc=scaling_doc)


def _app(db):
    app = FastAPI()
    r = APIRouter(prefix="/api")
    r.include_router(scaling_routes.build_router(db))
    app.include_router(r)
    return app


def test_readiness_locked_when_below_threshold():
    db = FakeDB(total=5, wins=4)  # 80% WR but only 5 trades
    client = TestClient(_app(db))
    r = client.get("/api/scaling/readiness")
    assert r.status_code == 200
    d = r.json()
    assert d["gate"]["clear"] is False
    assert d["gate"]["trades_ok"] is False  # 5 < 20
    assert d["gate"]["wr_ok"] is True       # 80 >= 40
    assert d["stats"]["closed_trades"] == 5
    assert d["stats"]["wins"] == 4
    assert d["stats"]["win_rate"] == 80.0
    assert len(d["current_instruments"]) == 5
    assert len(d["proposed_instruments"]) == 5
    assert len(d["scaled_instruments"]) == 10


def test_readiness_clear_when_threshold_met():
    db = FakeDB(total=25, wins=12)  # 48% WR, 25 trades
    client = TestClient(_app(db))
    d = client.get("/api/scaling/readiness").json()
    assert d["gate"]["clear"] is True
    assert d["gate"]["trades_ok"] is True
    assert d["gate"]["wr_ok"] is True


def test_promote_blocked_when_gate_locked():
    db = FakeDB(total=10, wins=5)  # 50% WR but only 10 trades
    client = TestClient(_app(db))
    r = client.post("/api/scaling/promote", json={"confirm": True})
    assert r.status_code == 409
    assert "gate not clear" in r.json()["detail"]


def test_promote_succeeds_when_gate_clear():
    db = FakeDB(total=30, wins=18)  # 60% WR, 30 trades
    client = TestClient(_app(db))
    r = client.post("/api/scaling/promote", json={"confirm": True})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "promoted"
    assert d["promoted"] is True
    assert len(d["instruments"]) == 10
    assert d["railway_env_command"].startswith("INSTRUMENTS=")
    # Was actually persisted
    assert db.scaling_state.replaced is not None
    assert db.scaling_state.replaced["promoted"] is True


def test_promote_requires_confirm():
    db = FakeDB(total=30, wins=18)
    client = TestClient(_app(db))
    r = client.post("/api/scaling/promote", json={"confirm": False})
    assert r.status_code == 400


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
