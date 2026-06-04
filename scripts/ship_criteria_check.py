"""Ship-criteria check for v0.3 promotion: headline + bucket bars."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crypto_predictor.logging_config import configure_logging

log = structlog.get_logger(__name__)

HEADLINE_HIT_RATE_TARGET = 0.625
HEADLINE_BRIER_TARGET = 0.226
BUCKET_TOLERANCE_PP = 10.0

BUCKETS = [
    (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70),
    (0.70, 0.75), (0.75, 0.80), (0.80, 0.95),
]


def check_headline_bar(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"hit_rate": 0.0, "brier": 0.0,
                "passes_hit_rate": False, "passes_brier": False}
    n = len(df)
    correct = int((df["status"] == "correct").sum())
    hit_rate = float(correct / n)
    labels = (df["status"] == "correct").astype(float).to_numpy()
    probs = df["p_direction"].to_numpy(dtype=float)
    brier = float(np.mean((probs - labels) ** 2))
    return {
        "hit_rate": hit_rate,
        "brier": brier,
        "passes_hit_rate": bool(hit_rate >= HEADLINE_HIT_RATE_TARGET),
        "passes_brier": bool(brier <= HEADLINE_BRIER_TARGET),
    }


def check_bucket_bar(df: pd.DataFrame, *,
                     min_samples_per_bucket: int = 20) -> dict:
    buckets_out: list[dict] = []
    for lo, hi in BUCKETS:
        sub = df[(df["p_direction"] >= lo) & (df["p_direction"] < hi)]
        n = len(sub)
        if n == 0:
            continue
        if n < min_samples_per_bucket:
            buckets_out.append({
                "lo": lo, "hi": hi, "n": n,
                "realized": float((sub["status"] == "correct").mean()),
                "expected": float(sub["p_direction"].mean()),
                "delta_pp": 0.0, "soft_pass": True,
            })
            continue
        realized = (sub["status"] == "correct").mean()
        expected = sub["p_direction"].mean()
        delta_pp = abs(realized - expected) * 100
        buckets_out.append({
            "lo": lo, "hi": hi, "n": n,
            "realized": float(realized),
            "expected": float(expected),
            "delta_pp": float(delta_pp),
            "soft_pass": False,
        })
    return {"buckets": buckets_out}


def evaluate(df: pd.DataFrame, *,
             min_samples_per_bucket: int = 20) -> dict:
    headline = check_headline_bar(df)
    buckets = check_bucket_bar(df,
                               min_samples_per_bucket=min_samples_per_bucket)
    failing_buckets = [
        b for b in buckets["buckets"]
        if not b.get("soft_pass") and b["delta_pp"] > BUCKET_TOLERANCE_PP
    ]
    can_ship = (
        headline["passes_hit_rate"] and headline["passes_brier"]
        and not failing_buckets
    )
    escalation = None
    if not headline["passes_hit_rate"] or not headline["passes_brier"]:
        escalation = "prior_alpha=5"
    elif failing_buckets:
        escalation = "manual_review_required"
    return {
        "headline": headline,
        "buckets": buckets["buckets"],
        "can_ship": can_ship,
        "escalation_recommendation": escalation,
    }


def format_telegram_message(result: dict) -> str:
    h = result["headline"]
    lines = ["\U0001f3af *v0.3 ship criteria check*"]
    lines.append(
        f"  Headline: {h['hit_rate'] * 100:.1f}% "
        f"({'PASS' if h['passes_hit_rate'] else 'FAIL'} >=62.5%)"
    )
    lines.append(
        f"  Brier: {h['brier']:.3f} "
        f"({'PASS' if h['passes_brier'] else 'FAIL'} <=0.226)"
    )
    for b in result["buckets"]:
        if b.get("soft_pass"):
            lines.append(f"  Bucket [{b['lo']:.2f},{b['hi']:.2f}): "
                         f"n={b['n']} (<20, soft pass)")
        else:
            status = "ok" if b["delta_pp"] <= BUCKET_TOLERANCE_PP else "FAIL"
            lines.append(
                f"  Bucket [{b['lo']:.2f},{b['hi']:.2f}): "
                f"{b['realized'] * 100:.0f}% vs expected "
                f"{b['expected'] * 100:.0f}% ({status})"
            )
    if result["can_ship"]:
        lines.append("\n✅ READY FOR PROMOTION")
        lines.append("Edit data/scheduler_config.yaml: mode=live, "
                     "calibration_version=0_3_0, tilt_weights_version=0_3_0")
    else:
        lines.append("\n❌ NOT READY")
        if result.get("escalation_recommendation"):
            lines.append(f"Recommended: {result['escalation_recommendation']}")
    return "\n".join(lines)


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("predictions.db"))
    parser.add_argument("--min-samples-per-bucket", type=int, default=20)
    args = parser.parse_args()
    import sqlite3
    conn = sqlite3.connect(str(args.db))
    df = pd.read_sql_query(
        "SELECT p_direction, status FROM predictions "
        "WHERE status IN ('correct','incorrect') AND mode='shadow' "
        "AND validated_at >= datetime('now', 'utc', '-7 days')",
        conn,
    )
    conn.close()
    result = evaluate(df, min_samples_per_bucket=args.min_samples_per_bucket)
    print(format_telegram_message(result))
    log.info("ship_criteria_result", can_ship=result["can_ship"])
    return 0 if result["can_ship"] else 2


if __name__ == "__main__":
    sys.exit(main())
