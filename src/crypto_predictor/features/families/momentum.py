"""Family 1 — momentum: multi-timeframe log returns, z-scored, plus consistency."""
from __future__ import annotations

import math

import numpy as np

from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.features.normalize import zscore


def _log_return(df, periods: int) -> float | None:
    if df.empty or len(df) <= periods:
        return None
    last = df["close"].iloc[-1]
    prev = df["close"].iloc[-1 - periods]
    if prev <= 0:
        return None
    return math.log(last / prev)


def _historical_returns(df, periods: int, max_samples: int = 1000) -> np.ndarray:
    closes = df["close"].values
    if len(closes) <= periods:
        return np.array([])
    rets = np.log(closes[periods:] / closes[:-periods])
    return rets[-max_samples:]


def compute_momentum_features(fetcher: FeatureFetcher,
                              symbol: str) -> dict[str, float]:
    feats: dict[str, float] = {}

    # 15m return → z-score against 90d 15m bars (90×96 = 8640)
    df15 = fetcher.ohlcv(symbol, "15m", lookback_bars=8640)
    r = _log_return(df15, 1)
    pop = _historical_returns(df15, 1)
    feats["ret_15m_z"] = zscore(r, pop) if r is not None else 0.0

    # 1h return → z-score against 90d 1h bars (2160)
    df1h = fetcher.ohlcv(symbol, "1h", lookback_bars=2200)
    r = _log_return(df1h, 1)
    pop = _historical_returns(df1h, 1)
    feats["ret_1h_z"] = zscore(r, pop) if r is not None else 0.0

    # 4h return → z-score against 90d 4h bars (540)
    df4h = fetcher.ohlcv(symbol, "4h", lookback_bars=600)
    r = _log_return(df4h, 1)
    pop = _historical_returns(df4h, 1)
    feats["ret_4h_z"] = zscore(r, pop) if r is not None else 0.0

    # 24h return → z-score against 90d 1d bars
    df1d = fetcher.ohlcv(symbol, "1d", lookback_bars=100)
    r = _log_return(df1d, 1)
    pop = _historical_returns(df1d, 1)
    feats["ret_24h_z"] = zscore(r, pop) if r is not None else 0.0

    # 7d return → z-score against 90d 1d bars, lag=7
    r = _log_return(df1d, 7)
    pop = _historical_returns(df1d, 7)
    feats["ret_7d_z"] = zscore(r, pop) if r is not None else 0.0

    # Momentum consistency: fraction of last 24×1h bars that went up
    if df1h.empty or len(df1h) < 25:
        feats["mom_consistency"] = 0.5
    else:
        last_25 = df1h.tail(25)
        diffs = last_25["close"].diff().dropna()
        ups = (diffs > 0).sum()
        feats["mom_consistency"] = float(ups) / len(diffs)

    return feats
