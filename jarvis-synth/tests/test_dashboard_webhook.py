"""Tests for the dashboard webhook (best-effort POST to JARVIS dashboard)."""
from __future__ import annotations

import json

import httpx
import pytest

from app.dashboard_webhook import post_lock_event


@pytest.mark.asyncio
async def test_no_op_when_url_missing():
    ok = await post_lock_event(
        webhook_url="",
        webhook_token="t",
        timestamp="2026-05-08T00:00:00+00:00",
        amount=500.0,
        nav_at_lock=100_500.0,
        baseline_before=100_000.0,
        baseline_after=100_500.0,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_no_op_when_token_missing():
    ok = await post_lock_event(
        webhook_url="https://example.com/api/broker/profit-locks",
        webhook_token="",
        timestamp="2026-05-08T00:00:00+00:00",
        amount=500.0,
        nav_at_lock=100_500.0,
        baseline_before=100_000.0,
        baseline_after=100_500.0,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_posts_with_correct_headers_and_body(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["token"] = request.headers.get("x-lock-token")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"stored": True, "duplicate": False})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.dashboard_webhook.httpx.AsyncClient",
        lambda *a, **kw: real_client(transport=transport),
    )

    ok = await post_lock_event(
        webhook_url="https://dash.example.com/api/broker/profit-locks",
        webhook_token="secret-token-xyz",
        timestamp="2026-05-08T01:23:45+00:00",
        amount=523.45,
        nav_at_lock=100_523.45,
        baseline_before=100_000.0,
        baseline_after=100_523.45,
    )

    assert ok is True
    assert captured["url"] == "https://dash.example.com/api/broker/profit-locks"
    assert captured["token"] == "secret-token-xyz"
    assert captured["body"] == {
        "timestamp": "2026-05-08T01:23:45+00:00",
        "amount": 523.45,
        "nav_at_lock": 100_523.45,
        "baseline_before": 100_000.0,
        "baseline_after": 100_523.45,
        "source": "jarvis-synth",
    }


@pytest.mark.asyncio
async def test_returns_false_on_non_2xx(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid lock token"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.dashboard_webhook.httpx.AsyncClient",
        lambda *a, **kw: real_client(transport=transport),
    )

    ok = await post_lock_event(
        webhook_url="https://dash.example.com/api/broker/profit-locks",
        webhook_token="wrong",
        timestamp="2026-05-08T01:23:45+00:00",
        amount=10.0,
        nav_at_lock=100_010.0,
        baseline_before=100_000.0,
        baseline_after=100_010.0,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_returns_false_on_network_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.dashboard_webhook.httpx.AsyncClient",
        lambda *a, **kw: real_client(transport=transport),
    )

    ok = await post_lock_event(
        webhook_url="https://dash.example.com/api/broker/profit-locks",
        webhook_token="t",
        timestamp="2026-05-08T01:23:45+00:00",
        amount=10.0,
        nav_at_lock=100_010.0,
        baseline_before=100_000.0,
        baseline_after=100_010.0,
    )
    assert ok is False
