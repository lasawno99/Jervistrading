"""LAYER 2 — TauricResearch-style multi-agent debate (adapted to forex + Claude).

Sequential pipeline:
  1. Fundamentals analyst — macro/policy lens
  2. Sentiment expert    — narrative + retail/social lens
  3. Technical analyst   — price action + indicators
  4. Bull researcher     — argues FOR upside
  5. Bear researcher     — argues FOR downside
  6. Trader              — synthesizes into BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL
  7. Risk manager        — final review; can downgrade or veto

Each agent is one Claude call. ~7 calls per instrument per cycle.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
import structlog
from anthropic import Anthropic

log = structlog.get_logger()

VERDICT_LEVELS = ("SELL", "UNDERWEIGHT", "HOLD", "OVERWEIGHT", "BUY")


@dataclass
class TauricVerdict:
    verdict: str            # SELL | UNDERWEIGHT | HOLD | OVERWEIGHT | BUY
    confidence: int         # 1..10
    fundamentals: str
    sentiment: str
    technical: str
    bull: str
    bear: str
    trader: str
    risk_manager: str


_FUND_SYSTEM = """You are the FUNDAMENTALS ANALYST in a forex desk.
Read the macro headlines and write a 3-4 sentence assessment focused on:
- Central bank policy bias (Fed/ECB/BoE/BoJ) for both legs of the pair
- Yield-spread direction
- Macro data trajectory (CPI, jobs, growth)
End with a clear "Net fundamentals tilt: bullish/neutral/bearish for [base currency]."
"""

_SENT_SYSTEM = """You are the SENTIMENT EXPERT in a forex desk.
Read the same headlines and write 3-4 sentences focused on:
- Crowd positioning narrative
- Recent surprise/fading themes
- Retail and institutional crowding signals from headline tone
End with: "Sentiment tilt: extended-long / building-long / mixed / building-short / extended-short."
"""

_TECH_SYSTEM = """You are the TECHNICAL ANALYST in a forex desk.
You'll be given recent OHLC candles and a Kronos-derived price-target context.
Write 3-4 sentences focused on:
- Trend structure (HH/HL vs LH/LL) over the recent window
- Momentum (where the last close sits vs short EMA-ish references)
- Notable levels (recent swings)
End with: "Technical tilt: trend-bullish / consolidation / trend-bearish."
"""

_BULL_SYSTEM = """You are the BULL RESEARCHER. Given the analysts' three reports
and the Kronos quant signal, build the strongest possible case for going LONG
this instrument. 4-5 sentences. Engage with what would invalidate you.
"""

_BEAR_SYSTEM = """You are the BEAR RESEARCHER. Given the same inputs and the
bull's argument, build the strongest possible case for going SHORT or
staying flat. 4-5 sentences. Punch holes in the bull case explicitly.
"""

_TRADER_SYSTEM = """You are the TRADER. You see all five prior reports.
Synthesize a single verdict.

Return ONLY valid JSON:
{
  "verdict": "SELL" | "UNDERWEIGHT" | "HOLD" | "OVERWEIGHT" | "BUY",
  "confidence": 1..10,
  "rationale": "1-2 sentences"
}

Decision rules:
- HOLD only when fundamentals/sentiment/technicals genuinely disagree OR all
  three are ambivalent. "Mixed picture" alone is NOT a reason to HOLD.
- If 2 of 3 analysts lean the same direction AND Kronos confirms,
  recommend at least OVERWEIGHT (long) or UNDERWEIGHT (short).
- If all 3 analysts AND Kronos align cleanly, recommend BUY/SELL.
- Confidence ≥ 7 requires real edge; don't inflate it.
"""

_RISK_SYSTEM = """You are the RISK MANAGER. Review the trader's verdict and
the full debate. You can:
  - confirm the trader's verdict
  - downgrade by one notch (e.g. BUY → OVERWEIGHT) if a specific risk
    materially changes the risk/reward
  - flip to HOLD only if the bear case credibly invalidates the entry
  - reduce confidence by 1-3 points

Do NOT downgrade reflexively. The trader has already weighed both sides.
Only intervene when you see something the trader missed or underweighted.

Return ONLY valid JSON:
{
  "final_verdict": "SELL" | "UNDERWEIGHT" | "HOLD" | "OVERWEIGHT" | "BUY",
  "final_confidence": 1..10,
  "review": "1 sentence — what you changed and why, or 'confirming' if no change"
}
"""


def _candle_summary(df: pd.DataFrame) -> str:
    if len(df) == 0:
        return "(no candles)"
    last = df.iloc[-1]
    first = df.iloc[0]
    high = float(df["high"].max())
    low = float(df["low"].min())
    pct = (float(last["close"]) - float(first["close"])) / float(first["close"]) * 100
    return (
        f"window: {len(df)} candles, "
        f"first close {float(first['close']):.5f} → last close {float(last['close']):.5f} "
        f"({pct:+.2f}%), range {low:.5f}-{high:.5f}, last 5 closes "
        f"{[round(float(x), 5) for x in df['close'].tail(5).tolist()]}"
    )


def _kronos_summary(kronos_signal) -> str:
    return (
        f"Kronos: direction={kronos_signal.direction} confidence={kronos_signal.confidence} "
        f"upside_prob={kronos_signal.upside_prob:.2%} vol_amp={kronos_signal.vol_amp:.2f}x "
        f"current={kronos_signal.current_price:.5f} target={kronos_signal.mean_target:.5f}"
    )


class TauricDebate:
    def __init__(self, api_key: str, model: str):
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def _ask(self, system: str, user: str, max_tokens: int = 600) -> str:
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:
            log.error("tauric_llm_failed", error=str(e))
            return ""
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()

    @staticmethod
    def _parse_json(raw: str) -> dict:
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].lstrip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.error("tauric_bad_json", raw=raw[:300])
            return {}

    async def run(
        self,
        instrument: str,
        macro_headlines: List[str],
        calendar: List[str],
        candles: pd.DataFrame,
        kronos_signal,
    ) -> Optional[TauricVerdict]:
        macro_block = (
            f"Instrument: {instrument}\n"
            f"Recent headlines:\n- " + "\n- ".join(macro_headlines or ["(none)"]) + "\n"
            "Economic calendar:\n- " + "\n- ".join(calendar or ["(none)"])
        )
        candles_block = f"Instrument: {instrument}\n{_candle_summary(candles)}\n{_kronos_summary(kronos_signal)}"

        # 1-3: Three analysts in parallel
        fund, sent, tech = await asyncio.gather(
            asyncio.to_thread(self._ask, _FUND_SYSTEM, macro_block),
            asyncio.to_thread(self._ask, _SENT_SYSTEM, macro_block),
            asyncio.to_thread(self._ask, _TECH_SYSTEM, candles_block),
        )
        if not (fund and sent and tech):
            return None

        analyst_pack = (
            f"FUNDAMENTALS:\n{fund}\n\nSENTIMENT:\n{sent}\n\nTECHNICAL:\n{tech}\n\n"
            f"KRONOS QUANT SIGNAL:\n{_kronos_summary(kronos_signal)}"
        )

        # 4: Bull
        bull = await asyncio.to_thread(self._ask, _BULL_SYSTEM, analyst_pack)
        if not bull:
            return None
        # 5: Bear (sees bull)
        bear_input = analyst_pack + f"\n\nBULL ARGUMENT:\n{bull}"
        bear = await asyncio.to_thread(self._ask, _BEAR_SYSTEM, bear_input)
        if not bear:
            return None

        # 6: Trader synthesis
        trader_input = (
            f"{analyst_pack}\n\nBULL:\n{bull}\n\nBEAR:\n{bear}\n\n"
            "Return JSON verdict."
        )
        trader_raw = await asyncio.to_thread(self._ask, _TRADER_SYSTEM, trader_input, max_tokens=400)
        trader_data = self._parse_json(trader_raw)
        if not trader_data:
            return None

        # 7: Risk Manager
        risk_input = (
            f"{analyst_pack}\n\nBULL:\n{bull}\n\nBEAR:\n{bear}\n\n"
            f"TRADER VERDICT:\n{json.dumps(trader_data)}\n\nReturn JSON review."
        )
        risk_raw = await asyncio.to_thread(self._ask, _RISK_SYSTEM, risk_input, max_tokens=400)
        risk_data = self._parse_json(risk_raw)
        if not risk_data:
            return None

        verdict = str(risk_data.get("final_verdict", "HOLD")).upper()
        if verdict not in VERDICT_LEVELS:
            verdict = "HOLD"
        confidence = int(risk_data.get("final_confidence", 5))
        confidence = max(1, min(10, confidence))

        return TauricVerdict(
            verdict=verdict,
            confidence=confidence,
            fundamentals=fund,
            sentiment=sent,
            technical=tech,
            bull=bull,
            bear=bear,
            trader=trader_data.get("rationale", ""),
            risk_manager=risk_data.get("review", ""),
        )
