"""Family 3 — volume/liquidity. Phase 1 covers volume_z; spread/depth in Week 7."""
from __future__ import annotations

from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.features.normalize import zscore


def compute_volume_features(fetcher: FeatureFetcher,
                            symbol: str) -> dict[str, float]:
    feats: dict[str, float] = {}
    df = fetcher.ohlcv(symbol, "1d", lookback_bars=35)
    if df.empty:
        feats["vol_z_24h"] = 0.0
        return feats
    latest_vol = float(df["volume"].iloc[-1])
    pop = df["volume"].values
    feats["vol_z_24h"] = zscore(latest_vol, pop)
    return feats
