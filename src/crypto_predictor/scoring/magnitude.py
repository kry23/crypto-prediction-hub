"""Magnitude estimator: base vol × signal strength × regime multiplier."""
from __future__ import annotations

import math

import numpy as np

from crypto_predictor.features.fetcher import FeatureFetcher

REGIME_MULT: dict[str, float] = {"BULL": 1.15, "BEAR": 0.90, "CHOP": 1.00}


def realized_vol_30d(fetcher: FeatureFetcher, symbol: str) -> float:
    """Std of daily log returns over the last 30 days. 0.0 if insufficient data."""
    df = fetcher.ohlcv(symbol, "1d", lookback_bars=32)
    if len(df) < 5:
        return 0.0
    closes = df["close"].values.astype(float)
    closes = closes[closes > 0]
    if len(closes) < 5:
        return 0.0
    rets = np.log(closes[1:] / closes[:-1])
    if len(rets) == 0:
        return 0.0
    return float(np.std(rets, ddof=0))


def compute_expected_return(fetcher: FeatureFetcher, symbol: str,
                            *, direction_raw: float, regime: str) -> float:
    """Compute signed expected return for next 24h horizon."""
    base_vol = realized_vol_30d(fetcher, symbol)
    if base_vol == 0:
        return 0.0
    strength = abs(direction_raw)
    regime_mult = REGIME_MULT.get(regime, 1.0)
    sign = math.copysign(1.0, direction_raw) if direction_raw != 0 else 0.0
    return base_vol * (0.5 + 0.5 * strength) * regime_mult * sign
