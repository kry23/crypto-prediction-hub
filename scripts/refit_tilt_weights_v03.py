"""Per-tilt x per-regime correlation analysis + recency-weighted weight refit."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import structlog
import yaml

# Project root onto sys.path so this script can run via
# `python scripts/refit_tilt_weights_v03.py` (same pattern as
# run_scheduler.py / predict_scan_cli.py / refit_calibration_v03.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_predictor.logging_config import configure_logging  # noqa: E402

log = structlog.get_logger(__name__)

TILTS = ["momentum", "perp", "volume", "technical", "sentiment", "global"]


def compute_per_tilt_correlations(
    df: pd.DataFrame, regime: str,
) -> dict[str, float]:
    sub = df[df["regime"] == regime]
    out: dict[str, float] = {}
    if "realized_return" not in sub.columns or len(sub) < 30:
        return out
    for tilt in TILTS:
        col = f"tilt_{tilt}"
        if col not in sub.columns:
            continue
        x = sub[col].to_numpy(dtype=float)
        y = sub["realized_return"].to_numpy(dtype=float)
        if x.std() == 0 or y.std() == 0:
            out[tilt] = 0.0
            continue
        # Weighted Pearson via centered cov
        w = sub["sample_weight"].to_numpy(dtype=float)
        wmean_x = (x * w).sum() / w.sum()
        wmean_y = (y * w).sum() / w.sum()
        cov = (w * (x - wmean_x) * (y - wmean_y)).sum() / w.sum()
        var_x = (w * (x - wmean_x) ** 2).sum() / w.sum()
        var_y = (w * (y - wmean_y) ** 2).sum() / w.sum()
        out[tilt] = cov / np.sqrt(var_x * var_y) if var_x and var_y else 0.0
    return out


def detect_sign_changes(
    *, new_correlations: dict[str, dict[str, float]],
    phase_1_5_weights: dict[str, dict[str, float]],
) -> list[dict]:
    changes = []
    for regime, corrs in new_correlations.items():
        old = phase_1_5_weights.get(regime, {})
        for tilt, new_corr in corrs.items():
            old_w = old.get(tilt, 0.0)
            old_sign = +1 if old_w >= 0 else -1
            new_sign = +1 if new_corr >= 0 else -1
            if old_sign != new_sign and abs(new_corr) > 0.05:
                changes.append({
                    "regime": regime, "tilt": tilt,
                    "old_sign": old_sign, "new_sign": new_sign,
                    "old_weight": old_w,
                    "correlation_v_0_3": new_corr,
                    "reason": f"sign_flip: {old_sign:+d} -> {new_sign:+d}, |corr|={abs(new_corr):.3f}",
                })
    return changes


def refit_weights(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Compute per-tilt weight per regime as the weighted Pearson correlation,
    normalized so weights sum to 1 in absolute value per regime."""
    out: dict[str, dict[str, float]] = {}
    for regime in df["regime"].unique():
        corrs = compute_per_tilt_correlations(df, regime)
        total = sum(abs(c) for c in corrs.values()) or 1.0
        out[regime] = {t: c / total for t, c in corrs.items()}
    return out


def _load_features_for_fit(db_path: Path) -> pd.DataFrame:
    """Load predictions + predictions_features joined and pivoted so each row
    has one column per tilt."""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    preds = pd.read_sql_query(
        "SELECT id, p_direction, target_value, actual_outcome, "
        "       status, regime, feature_completeness, mode, created_at "
        "FROM predictions "
        "WHERE status IN ('correct','incorrect') "
        "  AND actual_outcome IS NOT NULL",
        conn,
    )
    feats = pd.read_sql_query(
        "SELECT prediction_id, feature_name, raw_value, z_value "
        "FROM predictions_features",
        conn,
    )
    conn.close()
    # Pivot: each prediction_id has one row, columns are tilt_<name>
    tilt_features = ("momentum", "perp", "volume", "technical",
                      "sentiment", "global")
    feats_pivot = feats[
        feats["feature_name"].isin(tilt_features)
    ].pivot_table(
        index="prediction_id", columns="feature_name",
        values="z_value", aggfunc="mean",
    ).reset_index()
    feats_pivot.columns = ["prediction_id"] + [
        f"tilt_{c}" for c in feats_pivot.columns[1:]
    ]
    df = preds.merge(feats_pivot, left_on="id", right_on="prediction_id",
                      how="inner")
    df["realized_return"] = df["actual_outcome"]
    return df


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("predictions.db"))
    parser.add_argument("--out", type=Path,
                        default=Path("data/tilt_weights_0_3_0.yaml"))
    parser.add_argument("--shadow-weight", type=float, default=3.0)
    args = parser.parse_args()

    df = _load_features_for_fit(args.db)
    shadow = df[df["mode"] == "shadow"]
    backtest = df[df["mode"] == "live"]
    combined = pd.concat(
        [backtest.assign(sample_weight=1.0),
         shadow.assign(sample_weight=args.shadow_weight)],
        ignore_index=True,
    )
    log.info("dataset_loaded", n_total=len(combined),
             n_shadow=len(shadow), n_backtest=len(backtest))

    new_correlations = {
        regime: compute_per_tilt_correlations(combined, regime)
        for regime in combined["regime"].unique()
    }
    weights = refit_weights(combined)

    # Load Phase 1.5 weights for sign-change detection
    phase_1_5_path = Path("data/tilt_weights_phase_1_5.yaml")
    if phase_1_5_path.exists():
        phase_1_5_weights = yaml.safe_load(
            phase_1_5_path.read_text(encoding="utf-8")
        )["weights"]
    else:
        phase_1_5_weights = {}

    sign_changes = detect_sign_changes(
        new_correlations=new_correlations,
        phase_1_5_weights=phase_1_5_weights,
    )

    output = {
        "fit_window_backtest": (
            f"{backtest['created_at'].min()}..{backtest['created_at'].max()}"
            if not backtest.empty else "none"
        ),
        "fit_window_shadow": (
            f"{shadow['created_at'].min()}..{shadow['created_at'].max()}"
            if not shadow.empty else "none"
        ),
        "backtest_samples": len(backtest),
        "shadow_samples": len(shadow),
        "shadow_weight": args.shadow_weight,
        "weights": weights,
        "sign_changes": sign_changes,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(output, sort_keys=False),
                          encoding="utf-8")
    log.info("refit_tilts_complete",
             out=str(args.out), shadow_weight=args.shadow_weight,
             n_sign_changes=len(sign_changes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
