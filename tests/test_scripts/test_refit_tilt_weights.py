import pandas as pd
import pytest

from scripts.refit_tilt_weights_v03 import (
    compute_per_tilt_correlations,
    detect_sign_changes,
    refit_weights,
)


PHASE_1_5_WEIGHTS = {
    "BULL": {"momentum": 0.30, "perp": 0.20, "volume": 0.15,
              "technical": 0.15, "sentiment": 0.10, "global": 0.10},
    "CHOP": {"momentum": -0.25, "perp": 0.20, "volume": 0.15,
              "technical": 0.20, "sentiment": 0.10, "global": 0.10},
    "BEAR": {"momentum": 0.30, "perp": 0.20, "volume": 0.15,
              "technical": 0.15, "sentiment": 0.10, "global": 0.10},
}


def _fake_tilts_df(regime: str = "BULL", momentum_corr: float = 0.3,
                    n: int = 200) -> pd.DataFrame:
    import numpy as np
    rng = np.random.default_rng(0)
    mom = rng.normal(0, 1, n)
    realized = momentum_corr * mom + rng.normal(0, 1, n)
    return pd.DataFrame({
        "regime": [regime] * n,
        "tilt_momentum": mom,
        "tilt_perp": rng.normal(0, 1, n),
        "tilt_volume": rng.normal(0, 1, n),
        "tilt_technical": rng.normal(0, 1, n),
        "tilt_sentiment": rng.normal(0, 1, n),
        "tilt_global": rng.normal(0, 1, n),
        "realized_return": realized,
        "sample_weight": 1.0,
    })


def test_compute_per_tilt_correlations_returns_signed_values():
    df = _fake_tilts_df(regime="BULL", momentum_corr=0.5)
    corrs = compute_per_tilt_correlations(df, regime="BULL")
    assert "momentum" in corrs
    assert corrs["momentum"] > 0  # positive corr per setup


def test_detect_sign_changes_flips_chop_momentum():
    df = _fake_tilts_df(regime="CHOP", momentum_corr=+0.3)
    corrs = compute_per_tilt_correlations(df, regime="CHOP")
    changes = detect_sign_changes(
        new_correlations={"CHOP": corrs},
        phase_1_5_weights=PHASE_1_5_WEIGHTS,
    )
    # Phase 1.5 CHOP momentum sign = -1, new corr is +0.3 -> sign change
    assert any(c["regime"] == "CHOP" and c["tilt"] == "momentum"
                for c in changes)


def test_refit_weights_returns_per_regime_dict():
    df = pd.concat([_fake_tilts_df("BULL"), _fake_tilts_df("CHOP")])
    weights = refit_weights(df)
    assert "BULL" in weights
    assert "CHOP" in weights
    assert "momentum" in weights["BULL"]
    assert "sentiment" in weights["CHOP"]


def test_audit_includes_correlation_values():
    df = _fake_tilts_df(regime="CHOP", momentum_corr=+0.4)
    corrs = compute_per_tilt_correlations(df, regime="CHOP")
    changes = detect_sign_changes(
        new_correlations={"CHOP": corrs},
        phase_1_5_weights=PHASE_1_5_WEIGHTS,
    )
    for c in changes:
        assert "correlation_v_0_3" in c
        assert "old_sign" in c
        assert "new_sign" in c
