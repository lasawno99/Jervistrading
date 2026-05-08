"""Quick smoke test: synth matrix + guardrails (no LLM, no broker calls)."""
from __future__ import annotations

import os

import pytest

from app.guardrails import GuardrailState
from app.signal import Signal as KronosSignal
from app.synth import synthesize
from app.tauric import TauricVerdict


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("MAX_POSITION_UNITS", "1000")
    monkeypatch.setenv("DAILY_LOSS_LIMIT_PCT", "2")


def _kronos(direction="buy", confidence="high", upside=0.75, vol=1.1):
    return KronosSignal(
        instrument="EUR_USD", current_price=1.0800, mean_target=1.0850,
        upside_prob=upside, vol_amp=vol, direction=direction, confidence=confidence,
    )


def _tauric(verdict="BUY", confidence=8):
    return TauricVerdict(
        verdict=verdict, confidence=confidence,
        fundamentals="...", sentiment="...", technical="...",
        bull="...", bear="...", trader="...", risk_manager="...",
    )


def test_full_long_when_both_agree_buy():
    d = synthesize("EUR_USD", _tauric("BUY", 8), _kronos("buy", "high"), base_units=100)
    assert d.action == "LONG" and d.units == 100


def test_full_short_when_both_agree_sell():
    d = synthesize("EUR_USD", _tauric("SELL", 9), _kronos("sell", "high"), base_units=100)
    assert d.action == "SHORT" and d.units == 100


def test_hold_when_kronos_disagrees():
    d = synthesize("EUR_USD", _tauric("BUY", 8), _kronos("sell", "high"), base_units=100)
    assert d.action == "HOLD" and d.units == 0


def test_half_long_on_overweight_plus_kronos_buy():
    d = synthesize("EUR_USD", _tauric("OVERWEIGHT", 8), _kronos("buy", "medium"), base_units=100)
    assert d.action == "LONG" and d.units == 50


def test_half_long_when_buy_but_kronos_skips():
    d = synthesize("EUR_USD", _tauric("BUY", 8), _kronos("skip", "low"), base_units=100)
    # Kronos confidence "low" trips floor → HOLD
    assert d.action == "HOLD" and d.units == 0


def test_confidence_floor_low_tauric():
    d = synthesize("EUR_USD", _tauric("BUY", 4), _kronos("buy", "high"), base_units=100)
    assert d.action == "HOLD"


def test_hold_verdict_always_hold():
    d = synthesize("EUR_USD", _tauric("HOLD", 9), _kronos("buy", "high"), base_units=100)
    assert d.action == "HOLD"


def test_underweight_plus_sell_is_half_short():
    d = synthesize("EUR_USD", _tauric("UNDERWEIGHT", 7), _kronos("sell", "medium"), base_units=100)
    assert d.action == "SHORT" and d.units == 50
