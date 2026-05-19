"""/api/market/* — CoinMarketCap-backed market data for the dashboard."""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import cmc_client as cmc

log = logging.getLogger("market_routes")

router = APIRouter(prefix="/market", tags=["market"])


# ---------- response models ----------

class MoverItem(BaseModel):
    symbol: str
    name: str
    price: float
    change_24h: float
    change_7d: Optional[float] = None
    market_cap: Optional[float] = None


class TopMoversResponse(BaseModel):
    gainers: List[MoverItem] = Field(default_factory=list)
    losers: List[MoverItem] = Field(default_factory=list)
    fetched_at: float


class FearGreedResponse(BaseModel):
    value: int
    classification: str
    fetched_at: float


class RegimeResponse(BaseModel):
    regime: str  # bull | bear | chop
    btc_dominance: float
    total_market_cap_usd: float
    total_volume_24h_usd: float
    eth_dominance: Optional[float] = None
    fetched_at: float


# ---------- helpers ----------

def _now() -> float:
    import time
    return time.time()


# ---------- routes ----------

@router.get("/status")
async def market_status():
    return cmc.get_status()


@router.get("/top-movers", response_model=TopMoversResponse)
async def get_top_movers(limit: int = 100, top_n: int = 5):
    """Return top N 24h gainers and losers from the top `limit` coins by market cap."""
    try:
        data = await cmc.fetch(
            "/v1/cryptocurrency/listings/latest",
            {"start": 1, "limit": limit, "convert": "USD", "sort": "market_cap"},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    items: List[MoverItem] = []
    for row in data.get("data", []):
        q = (row.get("quote") or {}).get("USD") or {}
        ch24 = q.get("percent_change_24h")
        if ch24 is None:
            continue
        items.append(
            MoverItem(
                symbol=row.get("symbol") or "",
                name=row.get("name") or "",
                price=float(q.get("price") or 0.0),
                change_24h=float(ch24),
                change_7d=q.get("percent_change_7d"),
                market_cap=q.get("market_cap"),
            )
        )

    items.sort(key=lambda x: x.change_24h)
    losers = items[:top_n]
    gainers = list(reversed(items[-top_n:]))

    return TopMoversResponse(gainers=gainers, losers=losers, fetched_at=_now())


@router.get("/fear-greed", response_model=FearGreedResponse)
async def get_fear_greed():
    try:
        data = await cmc.fetch("/v3/fear-and-greed/latest", {})
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    d = data.get("data") or {}
    return FearGreedResponse(
        value=int(d.get("value") or 0),
        classification=str(d.get("value_classification") or "unknown"),
        fetched_at=_now(),
    )


@router.get("/regime", response_model=RegimeResponse)
async def get_regime():
    """Derive a simple bull/bear/chop label from CMC global metrics + Fear & Greed."""
    try:
        gm = await cmc.fetch("/v1/global-metrics/quotes/latest", {"convert": "USD"})
        fg = await cmc.fetch("/v3/fear-and-greed/latest", {})
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    d = gm.get("data") or {}
    q = (d.get("quote") or {}).get("USD") or {}
    btc_dom = float(d.get("btc_dominance") or 0.0)
    eth_dom = d.get("eth_dominance")
    total_mc = float(q.get("total_market_cap") or 0.0)
    vol24 = float(q.get("total_volume_24h") or 0.0)
    mc_pct_24h = q.get("total_market_cap_yesterday_percentage_change")
    fg_value = int((fg.get("data") or {}).get("value") or 50)

    # Simple regime classifier:
    #   bull  = market cap up >0.5% in 24h AND F&G >= 55
    #   bear  = market cap down <-0.5% in 24h OR F&G <= 30
    #   chop  = otherwise
    regime = "chop"
    if mc_pct_24h is not None:
        if mc_pct_24h > 0.5 and fg_value >= 55:
            regime = "bull"
        elif mc_pct_24h < -0.5 or fg_value <= 30:
            regime = "bear"

    return RegimeResponse(
        regime=regime,
        btc_dominance=btc_dom,
        eth_dominance=eth_dom,
        total_market_cap_usd=total_mc,
        total_volume_24h_usd=vol24,
        fetched_at=_now(),
    )
