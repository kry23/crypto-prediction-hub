"""Direction-raw scoring: weighted sum of 6 tilt functions."""
from __future__ import annotations

from crypto_predictor.scoring.tilt import (
    tilt_global, tilt_momentum, tilt_perp, tilt_sentiment,
    tilt_technical, tilt_volume,
)

DEFAULT_WEIGHTS: dict[str, float] = {
    "momentum": 0.20,
    "perp": 0.25,
    "volume": 0.10,
    "technical": 0.15,
    "sentiment": 0.15,
    "global": 0.15,
}


def compute_direction_raw(feats: dict, *,
                          weights: dict[str, float] | None = None) -> float:
    w = weights or DEFAULT_WEIGHTS

    mcap_w = float(feats.get("mcap_rank_weight", 1.0) or 1.0)
    btc_corr = float(feats.get("coin_btc_corr_30d", 0.0) or 0.0)
    global_attenuation = max(0.0, 1.0 - abs(btc_corr))

    raw = (
        w["momentum"]   * tilt_momentum(feats) +
        w["perp"]       * tilt_perp(feats) +
        w["volume"]     * tilt_volume(feats) +
        w["technical"]  * tilt_technical(feats) +
        w["sentiment"]  * tilt_sentiment(feats) * mcap_w +
        w["global"]     * tilt_global(feats) * global_attenuation
    )
    return max(-1.0, min(1.0, raw))
