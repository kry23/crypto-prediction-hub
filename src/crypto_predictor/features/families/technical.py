"""Family 4 — technical indicators (RSI, MACD, BB, SMA). ADX in Week 7."""
from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_predictor.features.fetcher import FeatureFetcher


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    diff = np.diff(closes)
    gains = np.where(diff > 0, diff, 0.0)
    losses = np.where(diff < 0, -diff, 0.0)
    avg_gain = gains[-period:].mean()
    avg_loss = losses[-period:].mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def _ema(arr: np.ndarray, period: int) -> np.ndarray:
    if len(arr) == 0:
        return arr
    alpha = 2 / (period + 1)
    out = np.empty_like(arr)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * arr[i] + (1 - alpha) * out[i - 1]
    return out


def _macd_hist(closes: np.ndarray) -> float:
    if len(closes) < 35:
        return 0.0
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = ema12 - ema26
    signal = _ema(macd, 9)
    return float(macd[-1] - signal[-1])


def _bb_position(closes: np.ndarray, period: int = 20, k: float = 2.0) -> float:
    if len(closes) < period:
        return 0.5
    window = closes[-period:]
    mid = window.mean()
    sd = window.std(ddof=0)
    upper = mid + k * sd
    lower = mid - k * sd
    if upper == lower:
        return 0.5
    return float((closes[-1] - lower) / (upper - lower))


def compute_technical_features(fetcher: FeatureFetcher,
                               symbol: str) -> dict[str, float]:
    feats: dict[str, float] = {}
    df = fetcher.ohlcv(symbol, "1h", lookback_bars=200)
    if df.empty:
        return {"rsi_14_1h": 50.0, "rsi_overbought": 0.0, "rsi_oversold": 0.0,
                "macd_hist_1h": 0.0, "bb_position_1h": 0.5,
                "price_vs_sma50": 0.0}
    closes = df["close"].values
    rsi = _rsi(closes, 14)
    feats["rsi_14_1h"] = rsi
    feats["rsi_overbought"] = 1.0 if rsi > 70 else 0.0
    feats["rsi_oversold"] = 1.0 if rsi < 30 else 0.0
    feats["macd_hist_1h"] = _macd_hist(closes)
    feats["bb_position_1h"] = _bb_position(closes)
    sma50 = closes[-50:].mean() if len(closes) >= 50 else closes.mean()
    feats["price_vs_sma50"] = float((closes[-1] / sma50) - 1.0) if sma50 else 0.0
    return feats
