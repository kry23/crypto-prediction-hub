"""Quick diagnostic for shadow-mode data accumulation progress.

Run any time during the v0.2.1 -> v0.3 dormant window to see:
- How many shadow predictions exist
- Breakdown by date / completeness / regime
- Hit rate on closed cohorts (which v0.3 calibration will fit on)

Useful as the "is shadow mode actually working?" check before kicking
off v0.3 plan execution.

Usage: `python scripts/shadow_status.py [--db predictions.db]`
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path


def load_shadow_rows(db_path: Path) -> list[dict]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, symbol, status, p_direction, target_value, "
            "       confidence_flag, regime, feature_completeness, "
            "       missing_features, calibration_version, created_at "
            "FROM predictions WHERE mode='shadow' ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def summarize(rows: list[dict]) -> dict:
    """Return aggregate stats over the shadow rows."""
    if not rows:
        return {"n_total": 0}
    n_total = len(rows)
    status_counts = Counter(r["status"] for r in rows)
    completeness_counts = Counter(r["feature_completeness"] for r in rows)
    regime_counts = Counter(r["regime"] for r in rows)
    calibration_versions = Counter(r["calibration_version"] for r in rows)

    closed = [r for r in rows if r["status"] in ("correct", "incorrect")]
    n_closed = len(closed)
    n_correct = sum(1 for r in closed if r["status"] == "correct")
    hit_rate = n_correct / n_closed if n_closed else 0.0

    # Date range
    dates = sorted({r["created_at"][:10] for r in rows})

    return {
        "n_total": n_total,
        "n_pending": status_counts.get("pending", 0),
        "n_correct": status_counts.get("correct", 0),
        "n_incorrect": status_counts.get("incorrect", 0),
        "n_expired": status_counts.get("expired", 0),
        "n_closed": n_closed,
        "hit_rate": hit_rate,
        "completeness_counts": dict(completeness_counts),
        "regime_counts": dict(regime_counts),
        "calibration_versions": dict(calibration_versions),
        "date_range": (dates[0], dates[-1]) if dates else (None, None),
        "n_days": len(dates),
    }


def render(summary: dict) -> str:
    if summary["n_total"] == 0:
        return "No shadow predictions yet — scheduler hasn't run or all are mode='live'."

    lines = []
    lines.append("=== Shadow data status ===")
    first, last = summary["date_range"]
    lines.append(f"  range:        {first} -> {last} ({summary['n_days']} day"
                  f"{'s' if summary['n_days'] != 1 else ''})")
    lines.append(f"  total rows:   {summary['n_total']}")
    lines.append(f"  pending:      {summary['n_pending']}")
    lines.append(f"  correct:      {summary['n_correct']}")
    lines.append(f"  incorrect:    {summary['n_incorrect']}")
    lines.append(f"  expired:      {summary['n_expired']}")
    if summary["n_closed"]:
        lines.append(
            f"  hit rate:     {summary['hit_rate'] * 100:.1f}% "
            f"({summary['n_correct']}/{summary['n_closed']} closed)"
        )

    lines.append("")
    lines.append("By feature_completeness:")
    for k, v in sorted(summary["completeness_counts"].items()):
        lines.append(f"  {k or 'NULL':10} {v}")

    lines.append("")
    lines.append("By regime:")
    for k, v in sorted(summary["regime_counts"].items()):
        lines.append(f"  {k or 'NULL':6} {v}")

    lines.append("")
    lines.append("Calibration versions:")
    for k, v in sorted(summary["calibration_versions"].items()):
        lines.append(f"  {k or 'NULL':22} {v}")

    lines.append("")
    target_days = 14
    if summary["n_days"] < target_days:
        lines.append(
            f"--> v0.3 calibration refit target: {target_days} days of shadow data. "
            f"Currently {summary['n_days']}/{target_days}."
        )
    else:
        lines.append(
            f"--> {summary['n_days']} days of shadow data accumulated -- "
            "v0.3 plan ready to execute."
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path,
                        default=Path(__file__).resolve().parent.parent
                                / "predictions.db")
    args = parser.parse_args()
    rows = load_shadow_rows(args.db)
    summary = summarize(rows)
    print(render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
