"""Family 2 — perp microstructure: funding, OI, L/S, liquidations."""
from __future__ import annotations

import numpy as np

from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.features.normalize import zscore


def compute_perp_features(fetcher: FeatureFetcher,
                          symbol: str) -> dict[str, float]:
    feats: dict[str, float] = {}

    # Funding
    f_df = fetcher.funding(symbol, lookback_rows=100)
    if not f_df.empty:
        latest = float(f_df["funding_rate"].iloc[-1])
        pop = f_df["funding_rate"].values
        feats["funding_z"] = zscore(latest, pop)
        feats["funding_extreme"] = 1.0 if abs(feats["funding_z"]) > 2.0 else 0.0
    else:
        feats["funding_z"] = 0.0
        feats["funding_extreme"] = 0.0

    # Open interest growth
    oi_df = fetcher.open_interest(symbol, lookback_rows=800)
    if len(oi_df) >= 25:
        now_oi = float(oi_df["open_interest"].iloc[-1])
        oi_24h_ago = float(oi_df["open_interest"].iloc[-25])
        growth = (now_oi / oi_24h_ago - 1.0) if oi_24h_ago > 0 else 0.0
        feats["oi_growth_24h"] = growth
        closes = oi_df["open_interest"].values
        growths = (closes[24:] / closes[:-24]) - 1.0 if len(closes) > 24 else np.array([])
        feats["oi_growth_z"] = zscore(growth, growths)
    else:
        feats["oi_growth_24h"] = 0.0
        feats["oi_growth_z"] = 0.0

    # Long/short ratio
    ls_df = fetcher.ls_ratio(symbol, lookback_rows=200)
    if not ls_df.empty:
        feats["ls_ratio"] = float(ls_df["ls_ratio"].iloc[-1])
        if len(ls_df) >= 49:  # 4h × 12 samples/hr at 5m
            ls_4h_ago = float(ls_df["ls_ratio"].iloc[-49])
            feats["ls_ratio_change_4h"] = feats["ls_ratio"] - ls_4h_ago
        else:
            feats["ls_ratio_change_4h"] = 0.0
    else:
        feats["ls_ratio"] = 1.0
        feats["ls_ratio_change_4h"] = 0.0

    # Liquidations (last 4h)
    liq_df = fetcher.liquidations(symbol, lookback_rows=2000)
    if not liq_df.empty:
        cutoff_ms = fetcher._asof_ms - 4 * 3600 * 1000
        liq_4h = liq_df[liq_df["timestamp"] >= cutoff_ms]
        feats["liq_pressure_long_4h"] = float(
            liq_4h[liq_4h["side"] == "sell"]["size_usdt"].sum()
        )
        feats["liq_pressure_short_4h"] = float(
            liq_4h[liq_4h["side"] == "buy"]["size_usdt"].sum()
        )
    else:
        feats["liq_pressure_long_4h"] = 0.0
        feats["liq_pressure_short_4h"] = 0.0

    # Taker buy/sell proxy: candle body / range
    h_df = fetcher.ohlcv(symbol, "1h", lookback_bars=2)
    if len(h_df) >= 1:
        row = h_df.iloc[-1]
        body = float(row["close"] - row["open"])
        total = float(row["high"] - row["low"]) or 1.0
        feats["taker_buy_sell_1h"] = max(0.0, min(1.0, 0.5 + (body / total) * 0.5))
    else:
        feats["taker_buy_sell_1h"] = 0.5

    return feats
