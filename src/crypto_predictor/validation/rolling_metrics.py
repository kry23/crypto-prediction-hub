"""Rolling metrics computation + persistence into metrics_rolling table."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

WINDOWS = {"7d": 7, "30d": 30, "90d": 90}
REGIMES = ["ALL", "BULL", "BEAR", "CHOP"]
DIRECTIONS = ["all", "long", "short"]


def _matches(row, regime, direction):
    _, prediction, _, row_regime, _ = row
    if regime != "ALL" and row_regime != regime:
        return False
    if direction == "long" and prediction != "up":
        return False
    if direction == "short" and prediction != "down":
        return False
    return True


def compute_top_k_alpha(top_k_returns, universe_returns) -> float:
    """Top-K mean return minus universe mean return."""
    if not top_k_returns or not universe_returns:
        return 0.0
    import statistics
    return statistics.mean(top_k_returns) - statistics.mean(universe_returns)


def _agg(rows, all_rows_for_universe):
    if not rows:
        return None
    n = len(rows)
    correct = sum(1 for r in rows if r[0] == "correct")
    hit_rate = correct / n
    mae_vals = [abs(r[4] - r[2]) for r in rows if r[4] is not None and r[2] is not None]
    mae = sum(mae_vals) / len(mae_vals) if mae_vals else 0.0

    # Top-K alpha (top 20% by |target_value|)
    sorted_by_signal = sorted(
        rows, key=lambda r: abs(r[2] or 0), reverse=True,
    )
    k = max(1, n // 5)
    top_k_actuals = [r[4] for r in sorted_by_signal[:k] if r[4] is not None]
    universe_actuals = [r[4] for r in all_rows_for_universe if r[4] is not None]
    alpha = compute_top_k_alpha(top_k_actuals, universe_actuals) if top_k_actuals else None

    return n, correct, hit_rate, mae, alpha


def update_rolling_metrics(*, predictions_db: Path, now: datetime) -> int:
    """Recompute and persist rolling metrics. Returns count of metric rows written."""
    conn = sqlite3.connect(str(predictions_db))
    try:
        rows_written = 0
        for win_label, days in WINDOWS.items():
            cutoff = (now - timedelta(days=days)).isoformat()
            raw = conn.execute(
                "SELECT status, prediction, target_value, regime, actual_outcome "
                "FROM predictions "
                "WHERE status IN ('correct','incorrect') AND validated_at >= ?",
                (cutoff,),
            ).fetchall()
            for regime in REGIMES:
                for direction in DIRECTIONS:
                    filt = [r for r in raw if _matches(r, regime, direction)]
                    agg = _agg(filt, raw)
                    if agg is None:
                        continue
                    n, correct, hit, mae, alpha = agg
                    conn.execute(
                        "INSERT OR REPLACE INTO metrics_rolling("
                        "window, regime, direction, n_predictions, n_correct, "
                        "hit_rate, mae, brier, topk_alpha, topk_alpha_btc, updated_at"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL, ?)",
                        (win_label, regime, direction, n, correct,
                         hit, mae, alpha, now.isoformat()),
                    )
                    rows_written += 1
        conn.commit()
        return rows_written
    finally:
        conn.close()


def load_rolling_metrics_from_db(predictions_db: Path) -> dict[str, dict]:
    """Load latest rolling-metrics rows for window='ALL'/direction='all' (for report rendering).

    Returns empty dict if DB doesn't exist or metrics_rolling table is empty.
    """
    if not predictions_db.exists():
        return {}
    conn = sqlite3.connect(str(predictions_db))
    try:
        rows = conn.execute(
            "SELECT window, hit_rate, n_predictions, COALESCE(topk_alpha, 0.0) "
            "FROM metrics_rolling "
            "WHERE regime='ALL' AND direction='all' "
            "ORDER BY window"
        ).fetchall()
        return {
            window: {"hit_rate": hr, "n": n, "alpha": alpha}
            for window, hr, n, alpha in rows
        }
    finally:
        conn.close()
