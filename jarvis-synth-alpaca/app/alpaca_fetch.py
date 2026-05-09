"""Alpaca market-data fetcher.

Pulls historical bars (OHLCV) for both stocks and crypto in a Pandas
DataFrame shaped exactly like Kronos expects:
    columns = [timestamp, open, high, low, close, volume]

Uses the official `alpaca-py` SDK so we get retries + paging for free.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import structlog

log = structlog.get_logger()


_ALPACA_TIMEFRAMES = {
    # short-hand → (TimeFrame from alpaca-py once imported, label)
    "1Min": ("Minute", 1),
    "5Min": ("Minute", 5),
    "15Min": ("Minute", 15),
    "1Hour": ("Hour", 1),
    "4Hour": ("Hour", 4),
    "1Day": ("Day", 1),
    "H1": ("Hour", 1),  # alias for OANDA-style notation
    "M5": ("Minute", 5),
    "D1": ("Day", 1),
}


def _is_crypto(symbol: str) -> bool:
    """Crypto symbols use 'BASE/QUOTE' notation (e.g. BTC/USD).
    Stock symbols are bare tickers ('NVDA'), no slash.
    """
    return "/" in symbol


class AlpacaFetcher:
    def __init__(self, api_key: str, secret_key: str):
        from alpaca.data.historical import (
            CryptoHistoricalDataClient,
            StockHistoricalDataClient,
        )

        self._stock_client = StockHistoricalDataClient(
            api_key=api_key, secret_key=secret_key
        )
        self._crypto_client = CryptoHistoricalDataClient(
            api_key=api_key, secret_key=secret_key
        )

    def fetch_candles(
        self,
        symbol: str,
        granularity: str,
        count: int,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        from alpaca.data.requests import (
            CryptoBarsRequest,
            StockBarsRequest,
        )
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        if granularity not in _ALPACA_TIMEFRAMES:
            raise ValueError(
                f"granularity {granularity!r} not in {list(_ALPACA_TIMEFRAMES)}"
            )
        unit_name, qty = _ALPACA_TIMEFRAMES[granularity]
        unit = {
            "Minute": TimeFrameUnit.Minute,
            "Hour": TimeFrameUnit.Hour,
            "Day": TimeFrameUnit.Day,
        }[unit_name]
        timeframe = TimeFrame(amount=qty, unit=unit)

        end = end or datetime.now(timezone.utc)
        # Generous lookback window so we never under-fetch (timeframe-aware)
        per_unit_minutes = (
            qty if unit_name == "Minute"
            else qty * 60 if unit_name == "Hour"
            else qty * 60 * 24
        )
        start = end - timedelta(minutes=per_unit_minutes * count * 3)

        if _is_crypto(symbol):
            req = CryptoBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=timeframe,
                start=start,
                end=end,
            )
            resp = self._crypto_client.get_crypto_bars(req)
        else:
            from alpaca.data.enums import DataFeed

            req = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=timeframe,
                start=start,
                end=end,
                feed=DataFeed.IEX,  # free-tier compatible; SIP requires paid plan
            )
            resp = self._stock_client.get_stock_bars(req)

        df = resp.df
        if df is None or df.empty:
            raise RuntimeError(f"no candles returned for {symbol} @ {granularity}")

        # alpaca-py returns a MultiIndex (symbol, timestamp); flatten
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level=0)

        df = df.reset_index().rename(columns={"timestamp": "timestamp"})
        # Ensure expected columns exist + ordering matches Kronos
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                raise RuntimeError(f"alpaca bars missing column {col!r} for {symbol}")
        # Kronos expects an `amount` column (turnover = price * volume).
        # Alpaca's bars don't include it for either crypto or stocks (IEX feed),
        # so synthesize it as close * volume — the standard fallback used by the
        # Kronos demo notebooks when an exchange omits dollar-volume.
        if "amount" not in df.columns:
            df["amount"] = df["close"] * df["volume"]
        out = df[["timestamp", "open", "high", "low", "close", "volume", "amount"]].copy()
        out = out.tail(count).reset_index(drop=True)
        log.info(
            "alpaca_candles_fetched",
            symbol=symbol,
            granularity=granularity,
            rows=len(out),
            start=str(out.iloc[0]["timestamp"]) if len(out) else None,
            end=str(out.iloc[-1]["timestamp"]) if len(out) else None,
        )
        return out
