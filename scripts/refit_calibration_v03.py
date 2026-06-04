"""Re-fit calibration on backtest + recency-weighted shadow data.

Outputs `data/calibration_0_3_0.json`. Per (completeness, regime).
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import structlog
from sklearn.isotonic import IsotonicRegression

# Project root onto sys.path so this script can run via
# `python scripts/refit_calibration_v03.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_predictor.calibration.per_completeness import (  # noqa: E402
    PerCompletenessCalibration,
    save_per_completeness,
)
from crypto_predictor.calibration.v03_pipeline import (  # noqa: E402
    fit_smoothed_isotonic,
)
from crypto_predictor.logging_config import configure_logging  # noqa: E402

log = structlog.get_logger(__name__)

MIN_SAMPLES_PER_FIT = 30


def weighted_concat(
    *,
    backtest: pd.DataFrame,
    shadow: pd.DataFrame,
    shadow_weight: float,
) -> pd.DataFrame:
    bk = backtest.copy()
    sh = shadow.copy()
    bk["sample_weight"] = 1.0
    sh["sample_weight"] = shadow_weight
    return pd.concat([bk, sh], ignore_index=True)


def _fit_one_group(
    group: pd.DataFrame, *, prior_alpha: float, prior_beta: float,
) -> dict:
    """Fit weighted isotonic then smooth knots then re-fit."""
    x = group["direction_raw"].to_numpy()
    y = group["outcome"].astype(float).to_numpy()
    w = group["sample_weight"].astype(float).to_numpy()
    ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
    ir.fit(x, y, sample_weight=w)
    knot_x = ir.X_thresholds_.tolist()
    knot_y = ir.y_thresholds_.tolist()
    # n per knot = sum of weights in [knot_x[i], knot_x[i+1])
    n_per_knot = []
    for i in range(len(knot_x)):
        if i < len(knot_x) - 1:
            mask = (x >= knot_x[i]) & (x < knot_x[i + 1])
        else:
            mask = x >= knot_x[i]
        n_per_knot.append(int(w[mask].sum()))
    return fit_smoothed_isotonic(
        x=knot_x,
        y=knot_y,
        n_per_knot=n_per_knot,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
    )


def fit_per_completeness_calibration(
    df: pd.DataFrame,
    *,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
    fit_window: str = "unspecified",
) -> PerCompletenessCalibration:
    by_completeness: dict[str, dict[str, dict]] = {}
    for completeness in ("full", "degraded"):
        comp_df = df[df["feature_completeness"] == completeness]
        regimes: dict[str, dict] = {}
        for regime in ("BULL", "CHOP", "BEAR"):
            grp = comp_df[comp_df["regime"] == regime]
            if len(grp) < MIN_SAMPLES_PER_FIT:
                log.info(
                    "skip_sparse_group",
                    completeness=completeness,
                    regime=regime,
                    n=len(grp),
                )
                continue
            regimes[regime] = _fit_one_group(
                grp, prior_alpha=prior_alpha, prior_beta=prior_beta,
            )
        by_completeness[completeness] = regimes
    return PerCompletenessCalibration(
        fit_window=fit_window,
        by_completeness=by_completeness,
        smoothing={"prior_alpha": prior_alpha, "prior_beta": prior_beta},
        extrapolation={"cap": 1.0},
    )


def load_predictions_for_fit(db_path: Path) -> pd.DataFrame:
    """Load closed predictions (status in correct/incorrect) with outcome label."""
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql_query(
        "SELECT p_direction, target_value, status, "
        "       confidence_flag, regime, feature_completeness, mode, "
        "       symbol, created_at "
        "FROM predictions "
        "WHERE status IN ('correct','incorrect')",
        conn,
    )
    conn.close()
    df["outcome"] = (df["status"] == "correct").astype(int)
    # Approximation: direction_raw is not stored; use 2*p_direction - 1 as proxy
    # (this is the inverse of the calibration applied; only used for re-fit)
    df["direction_raw"] = 2.0 * df["p_direction"] - 1.0
    return df


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("predictions.db"))
    parser.add_argument(
        "--out", type=Path, default=Path("data/calibration_0_3_0.json"),
    )
    parser.add_argument("--shadow-weight", type=float, default=3.0)
    parser.add_argument("--prior-alpha", type=float, default=1.0)
    parser.add_argument("--prior-beta", type=float, default=1.0)
    args = parser.parse_args()

    df = load_predictions_for_fit(args.db)
    shadow = df[df["mode"] == "shadow"]
    # treat the 2026-06-02 live cohort as historical
    backtest = df[df["mode"] == "live"]
    combined = weighted_concat(
        backtest=backtest, shadow=shadow, shadow_weight=args.shadow_weight,
    )
    log.info(
        "dataset_summary",
        n_total=len(combined),
        n_backtest=len(backtest),
        n_shadow=len(shadow),
    )

    fit_window = (
        f"{combined['created_at'].min()}..{combined['created_at'].max()}"
    )
    cal = fit_per_completeness_calibration(
        combined,
        prior_alpha=args.prior_alpha,
        prior_beta=args.prior_beta,
        fit_window=fit_window,
    )
    save_per_completeness(cal, args.out)
    log.info(
        "calibration_saved",
        path=str(args.out),
        completenesses=list(cal.by_completeness.keys()),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
