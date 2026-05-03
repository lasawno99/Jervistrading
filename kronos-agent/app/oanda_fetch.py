"""Read-only OANDA candle fetcher. No trading here."""
from __future__ import annotations

from typing import List

import pandas as pd
from oandapyV20 import API
from oandapyV20.endpoints import instruments as v20_instruments


class OandaFetcher:
    def __init__(self, api_token: str, environment: str):
        if environment != "practice":
            raise RuntimeError("kronos-agent uses practice only")
        self._client = API(access_token=api_token, environment="practice")

    def fetch_candles(
        self, instrument: str, granularity: str, count: int
    ) -> pd.DataFrame:
        count = max(1, min(int(count), 5000))
        req = v20_instruments.InstrumentsCandles(
            instrument=instrument,
            params={"granularity": granularity, "count": count, "price": "M"},
        )
        resp = self._client.request(req)
        rows: List[dict] = []
        for c in resp.get("candles", []):
            if not c.get("complete", False):
                continue
            m = c.get("mid", {})
            rows.append(
                {
                    "timestamps": pd.to_datetime(c["time"]),
                    "open": float(m["o"]),
                    "high": float(m["h"]),
                    "low": float(m["l"]),
                    "close": float(m["c"]),
                    "volume": float(c.get("volume", 0) or 0),
                    "amount": float(c.get("volume", 0) or 0) * float(m["c"]),
                }
            )
        df = pd.DataFrame(rows)
        if df.empty:
            raise RuntimeError(f"No candles returned for {instrument}")
        return df
