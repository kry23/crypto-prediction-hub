from pathlib import Path

import pandas as pd
import pytest

from scripts.refit_calibration_v03 import (
    weighted_concat,
    fit_per_completeness_calibration,
)


def _fake_predictions(
    n: int = 100,
    completeness: str = "full",
    regime: str = "BULL",
    hit_rate: float = 0.65,
) -> pd.DataFrame:
    import numpy as np
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "direction_raw": rng.uniform(-0.5, 0.5, n),
        "p_direction": rng.uniform(0.5, 0.9, n),
        "outcome": (rng.uniform(0, 1, n) < hit_rate).astype(int),
        "feature_completeness": [completeness] * n,
        "regime": [regime] * n,
    })


def test_weighted_concat_multiplies_shadow_rows():
    backtest = _fake_predictions(n=10)
    shadow = _fake_predictions(n=5)
    combined = weighted_concat(
        backtest=backtest, shadow=shadow, shadow_weight=3.0,
    )
    # weighted_concat should produce a weight column
    assert "sample_weight" in combined.columns
    # Backtest rows weight 1, shadow rows weight 3
    assert (combined.iloc[:10]["sample_weight"] == 1.0).all()
    assert (combined.iloc[10:]["sample_weight"] == 3.0).all()


def test_fit_per_completeness_populates_both_full_and_degraded():
    full_df = _fake_predictions(n=200, completeness="full", regime="BULL")
    degraded_df = _fake_predictions(
        n=50, completeness="degraded", regime="BULL", hit_rate=0.4,
    )
    combined = pd.concat([full_df, degraded_df], ignore_index=True)
    combined["sample_weight"] = 1.0
    cal = fit_per_completeness_calibration(combined)
    assert "full" in cal.by_completeness
    assert "degraded" in cal.by_completeness
    assert "BULL" in cal.by_completeness["full"]
    assert "BULL" in cal.by_completeness["degraded"]


def test_fit_sparse_regime_skipped_for_degraded():
    # full has BULL+BEAR; degraded has only BULL
    full = pd.concat([
        _fake_predictions(n=100, completeness="full", regime="BULL"),
        _fake_predictions(n=100, completeness="full", regime="BEAR"),
    ])
    degraded = _fake_predictions(n=50, completeness="degraded", regime="BULL")
    combined = pd.concat([full, degraded], ignore_index=True)
    combined["sample_weight"] = 1.0
    cal = fit_per_completeness_calibration(combined)
    assert "BEAR" in cal.by_completeness["full"]
    assert "BEAR" not in cal.by_completeness["degraded"]


def test_recency_weighted_shadow_dominates():
    """When shadow data has very different outcome rate, with high weight
    it should pull the fit toward the shadow distribution."""
    backtest = _fake_predictions(n=100, hit_rate=0.65)
    shadow = _fake_predictions(n=100, hit_rate=0.35)
    combined = weighted_concat(
        backtest=backtest, shadow=shadow, shadow_weight=10.0,
    )
    cal = fit_per_completeness_calibration(combined)
    # With shadow heavily weighted, mid-knot y should be biased toward 0.35
    fit = cal.by_completeness["full"]["BULL"]
    # Average of fitted y should be closer to 0.35 than 0.65
    avg_y = sum(fit["y"]) / len(fit["y"])
    assert avg_y < 0.55
