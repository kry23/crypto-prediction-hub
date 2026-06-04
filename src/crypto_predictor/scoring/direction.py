"""Direction-raw scoring: weighted sum of 6 tilt functions."""
from __future__ import annotations

from pathlib import Path

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


def calibrate_direction(
    *,
    calibration_path: Path | None,
    direction_raw: float,
    regime: str,
    feature_completeness: str = "full",
) -> float:
    """Map ``direction_raw`` to a calibrated P(up) for the given regime.

    Detects the calibration JSON format on disk and dispatches:

    * ``per_completeness`` (v0.3): uses
      :func:`crypto_predictor.calibration.per_completeness.lookup_calibrated_probability`
      with the supplied ``feature_completeness`` (falls back to ``"full"``
      internally if the bucket is empty for the regime).
    * ``legacy`` (Plan B / v1.5): uses
      :func:`crypto_predictor.calibration.isotonic.predict_probability`.
    * ``missing`` (no file, or unparseable, or unrecognised schema):
      returns 0.5 — uncalibrated 50/50.

    A ``None`` path is treated as missing. This keeps shadow runs and
    older deployments working unchanged while activating the v0.3 lookup
    the moment ``data/calibration_0_3_0.json`` lands on disk.
    """
    # Lazy imports so the scoring module stays cheap to import at startup
    # and doesn't drag sklearn in for callers that only need tilts.
    from crypto_predictor.calibration.isotonic import (
        predict_probability,
    )
    from crypto_predictor.calibration.per_completeness import (
        load_per_completeness, lookup_calibrated_probability,
    )
    from crypto_predictor.calibration.persistence import (
        detect_calibration_format, load_calibration,
    )

    if calibration_path is None:
        return 0.5

    fmt = detect_calibration_format(calibration_path)
    if fmt == "per_completeness":
        cal = load_per_completeness(calibration_path)
        if cal is None:
            return 0.5
        try:
            return lookup_calibrated_probability(
                cal,
                completeness=feature_completeness,
                regime=regime,
                direction_raw=direction_raw,
            )
        except KeyError:
            # No fit for this (completeness, regime) AND no fallback in 'full'.
            return 0.5
    if fmt == "legacy":
        calibs = load_calibration(calibration_path)
        return predict_probability(
            calibs, raw_score=direction_raw, regime=regime,
        )
    return 0.5
