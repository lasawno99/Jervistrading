"""Thin wrapper around the Kronos predictor with lazy model load."""
from __future__ import annotations

from typing import Optional

import pandas as pd
import structlog
import torch

log = structlog.get_logger()

_SIZE_TO_HF = {
    "mini": ("NeoQuasar/Kronos-Tokenizer-base", "NeoQuasar/Kronos-mini"),
    "small": ("NeoQuasar/Kronos-Tokenizer-base", "NeoQuasar/Kronos-small"),
    "base": ("NeoQuasar/Kronos-Tokenizer-base", "NeoQuasar/Kronos-base"),
}


class KronosForecaster:
    def __init__(self, size: str = "small", max_context: int = 512):
        self._size = size
        self._max_context = max_context
        self._predictor = None  # lazy

    def _ensure_loaded(self) -> None:
        if self._predictor is not None:
            return
        # Imported lazily so the module import path is correct at boot.
        # (The Kronos repo is cloned into /app/Kronos and put on PYTHONPATH.)
        from model import Kronos, KronosPredictor, KronosTokenizer

        tokenizer_id, model_id = _SIZE_TO_HF[self._size]
        log.info("kronos_loading", tokenizer=tokenizer_id, model=model_id)
        tokenizer = KronosTokenizer.from_pretrained(tokenizer_id)
        model = Kronos.from_pretrained(model_id)
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self._predictor = KronosPredictor(
            model, tokenizer, device=device, max_context=self._max_context
        )
        log.info("kronos_loaded", device=device)

    def predict(
        self,
        df: pd.DataFrame,
        lookback: int,
        pred_len: int,
        sample_count: int = 20,
        temperature: float = 1.0,
        top_p: float = 0.95,
    ) -> pd.DataFrame:
        self._ensure_loaded()
        if len(df) < lookback:
            raise RuntimeError(f"Need {lookback} rows, got {len(df)}")

        x_df = df.loc[: lookback - 1, ["open", "high", "low", "close", "volume", "amount"]]
        x_ts = df.loc[: lookback - 1, "timestamps"]

        # Extrapolate y timestamps at the inferred frequency of x_ts.
        if len(x_ts) >= 2:
            freq = x_ts.iloc[-1] - x_ts.iloc[-2]
        else:
            freq = pd.Timedelta(hours=1)
        y_ts = pd.Series(
            [x_ts.iloc[-1] + freq * (i + 1) for i in range(pred_len)],
            name="timestamps",
        )

        return self._predictor.predict(
            df=x_df,
            x_timestamp=x_ts,
            y_timestamp=y_ts,
            pred_len=pred_len,
            T=temperature,
            top_p=top_p,
            sample_count=sample_count,
        )
