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

# Per-regime weights (data-driven from Phase 1.5 correlation analysis)
# Notes:
# - sentiment and global caches are empty in current backtest -> weight = 0
# - tilt_momentum correlation flips sign across regimes -> handled via MOMENTUM_FLIP_BY_REGIME
# - Weights intentionally sum to less than 1.0 because sentiment+global are zero.
#   compute_direction_raw_for_regime normalizes them to sum-to-1 internally.
#   When sentiment/global caches become populated, restore 0.10 each.
DEFAULT_REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "BULL": {
        "momentum": 0.35,
        "perp": 0.05,
        "volume": 0.05,
        "technical": 0.15,
        "sentiment": 0.00,
        "global": 0.00,
    },
    "CHOP": {
        "momentum": 0.20,
        "perp": 0.05,
        "volume": 0.05,
        "technical": 0.50,
        "sentiment": 0.00,
        "global": 0.00,
    },
    "BEAR": {  # Unmeasured; safer to lean technical (less direction-dependent)
        "momentum": 0.10,
        "perp": 0.10,
        "volume": 0.05,
        "technical": 0.50,
        "sentiment": 0.00,
        "global": 0.00,
    },
}

# Sign flip for tilts whose correlation is regime-opposite
# CHOP shows negative momentum correlation -> invert (mean-reversion)
MOMENTUM_FLIP_BY_REGIME: dict[str, float] = {
    "BULL": 1.0,
    "CHOP": -1.0,  # mean-reversion in chop
    "BEAR": 1.0,
}


def compute_direction_raw_for_regime(feats: dict, regime: str) -> float:
    """Pick regime-specific weights and apply tilt-sign flip, then compute direction."""
    weights = DEFAULT_REGIME_WEIGHTS.get(regime, DEFAULT_WEIGHTS)
    # Normalize to sum to 1.0 (some weights may be 0 if their cache is empty)
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    momentum_flip = MOMENTUM_FLIP_BY_REGIME.get(regime, 1.0)
    if momentum_flip != 1.0:
        # Compute manually with the flipped momentum tilt
        mcap_w = float(feats.get("mcap_rank_weight", 1.0) or 1.0)
        btc_corr = float(feats.get("coin_btc_corr_30d", 0.0) or 0.0)
        global_attenuation = max(0.0, 1.0 - abs(btc_corr))
        raw = (
            weights["momentum"]  * tilt_momentum(feats) * momentum_flip +
            weights["perp"]      * tilt_perp(feats) +
            weights["volume"]    * tilt_volume(feats) +
            weights["technical"] * tilt_technical(feats) +
            weights["sentiment"] * tilt_sentiment(feats) * mcap_w +
            weights["global"]    * tilt_global(feats) * global_attenuation
        )
        return max(-1.0, min(1.0, raw))
    return compute_direction_raw(feats, weights=weights)


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
