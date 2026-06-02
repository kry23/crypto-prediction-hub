"""Regime detector: BULL / BEAR / CHOP based on BTC trend + funding + global mcap."""
from __future__ import annotations

import math
from typing import Literal

from crypto_predictor.features.fetcher import FeatureFetcher

REGIME_LABELS = ("BULL", "BEAR", "CHOP")
Regime = Literal["BULL", "BEAR", "CHOP"]


def detect_regime(fetcher: FeatureFetcher, *,
                  global_mcap_trend: float = 0.0,
                  btc_symbol: str = "BTC/USDT:USDT") -> Regime:
    """Detect market regime via BTC 30d return + funding + global mcap voting."""
    daily = fetcher.ohlcv(btc_symbol, "1d", lookback_bars=32)
    btc_30d_return = 0.0
    if len(daily) >= 31:
        p_now = float(daily["close"].iloc[-1])
        p_30d = float(daily["close"].iloc[-31])
        if p_30d > 0:
            btc_30d_return = math.log(p_now / p_30d)

    funding = fetcher.funding(btc_symbol, lookback_rows=21)
    if not funding.empty:
        btc_funding_avg = float(funding["funding_rate"].mean())
    else:
        btc_funding_avg = 0.0

    bull_votes = (
        (1 if btc_30d_return > 0.05 else 0) +
        (1 if btc_funding_avg > 0 else 0) +
        (1 if global_mcap_trend > 0 else 0)
    )
    bear_votes = (
        (1 if btc_30d_return < -0.05 else 0) +
        (1 if btc_funding_avg < -0.0001 else 0) +
        (1 if global_mcap_trend < 0 else 0)
    )

    if bull_votes >= 2:
        return "BULL"
    if bear_votes >= 2:
        return "BEAR"
    return "CHOP"
