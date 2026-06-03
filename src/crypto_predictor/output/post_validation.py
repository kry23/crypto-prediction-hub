"""Post-validation summary: hit rate by flag/regime/direction + Telegram digest.

Runs after `_job_validate_pending` closes a non-empty cohort. Surfaces the
first observable signal — does the live model match the backtest baseline? —
without the user having to manually run the analysis scripts.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def _brier(probs: list[float], labels: list[int]) -> float:
    if not probs:
        return 0.0
    return sum((p - l) ** 2 for p, l in zip(probs, labels)) / len(probs)


def summarize_recent_closures(*, db_path: Path, since: datetime
                                ) -> dict:
    """Aggregate closed predictions where `validated_at >= since`.

    Returns dict with: n_closed, hit_rate, brier, by_flag, by_regime,
    by_direction. Empty if no closures in window.
    """
    if not db_path.exists():
        return {"n_closed": 0}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT confidence_flag, regime, prediction, status, "
            "p_direction, target_value, actual_outcome, evaluation, "
            "symbol, validated_at "
            "FROM predictions "
            "WHERE status IN ('correct','incorrect') "
            "AND validated_at >= ?",
            (since.isoformat(),),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"n_closed": 0}

    n_total = len(rows)
    n_correct = sum(1 for r in rows if r["status"] == "correct")
    probs = [r["p_direction"] for r in rows]
    labels = [1 if r["status"] == "correct" else 0 for r in rows]
    brier = _brier(probs, labels)

    def _group_rate(key: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for r in rows:
            k = r[key]
            d = out.setdefault(k, {"n": 0, "correct": 0})
            d["n"] += 1
            if r["status"] == "correct":
                d["correct"] += 1
        for d in out.values():
            d["hit_rate"] = _safe_div(d["correct"], d["n"])
        return out

    return {
        "n_closed": n_total,
        "n_correct": n_correct,
        "hit_rate": _safe_div(n_correct, n_total),
        "brier": brier,
        "by_flag": _group_rate("confidence_flag"),
        "by_regime": _group_rate("regime"),
        "by_direction": _group_rate("prediction"),
    }


def format_validation_telegram(summary: dict, *,
                                  backtest_brier_baseline: float = 0.226,
                                  backtest_hit_baseline: float = 0.625,
                                  ) -> str:
    """Render a compact Telegram digest from summarize_recent_closures()."""
    if summary.get("n_closed", 0) == 0:
        return ""

    lines = ["📊 *Validation cycle complete*"]
    n = summary["n_closed"]
    hr = summary["hit_rate"]
    br = summary["brier"]
    hr_diff = hr - backtest_hit_baseline
    br_diff = br - backtest_brier_baseline
    hr_arrow = "▲" if hr_diff >= 0 else "▼"
    br_arrow = "▼" if br_diff <= 0 else "▲"  # lower brier is better

    lines.append(
        f"Closed: {n}   Hit: {hr * 100:.1f}% {hr_arrow}{abs(hr_diff) * 100:.1f}pp"
    )
    lines.append(
        f"Brier: {br:.3f} {br_arrow}{abs(br_diff):.3f} vs 0.226"
    )

    if summary.get("by_flag"):
        lines.append("\nBy flag:")
        for flag in sorted(summary["by_flag"]):
            d = summary["by_flag"][flag]
            lines.append(
                f"  {flag}: {d['correct']}/{d['n']} ({d['hit_rate'] * 100:.0f}%)"
            )
    if summary.get("by_regime"):
        lines.append("\nBy regime:")
        for regime in sorted(summary["by_regime"]):
            d = summary["by_regime"][regime]
            lines.append(
                f"  {regime}: {d['correct']}/{d['n']} ({d['hit_rate'] * 100:.0f}%)"
            )
    if summary.get("by_direction"):
        lines.append("\nBy direction:")
        for direction in sorted(summary["by_direction"]):
            d = summary["by_direction"][direction]
            lines.append(
                f"  {direction}: {d['correct']}/{d['n']} "
                f"({d['hit_rate'] * 100:.0f}%)"
            )

    return "\n".join(lines)


def lookback_window(now: datetime, hours: int = 24) -> datetime:
    return now - timedelta(hours=hours)
