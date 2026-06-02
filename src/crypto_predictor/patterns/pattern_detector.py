"""Mine simple patterns from closed predictions."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)


def _classify(win_rate: float, seek_threshold: float = 0.65,
              avoid_threshold: float = 0.50) -> str:
    if win_rate > seek_threshold:
        return "SEEK"
    if win_rate < avoid_threshold:
        return "AVOID"
    return "NEUTRAL"


def detect_and_upsert_patterns(*, predictions_db: Path,
                                now: datetime, lookback_days: int = 30,
                                min_occurrences: int = 5) -> int:
    """Detect simple patterns over the last `lookback_days` of closed predictions."""
    cutoff = (now - timedelta(days=lookback_days)).isoformat()
    conn = sqlite3.connect(str(predictions_db))
    try:
        # Cohort 1: confidence_flag × regime
        rows = conn.execute(
            "SELECT confidence_flag, regime, status FROM predictions "
            "WHERE status IN ('correct','incorrect') AND validated_at >= ?",
            (cutoff,),
        ).fetchall()
        cohorts: dict[tuple, list[str]] = {}
        for flag, regime, status in rows:
            cohorts.setdefault((flag, regime), []).append(status)

        n_written = 0
        for (flag, regime), statuses in cohorts.items():
            if len(statuses) < min_occurrences:
                continue
            wins = sum(1 for s in statuses if s == "correct")
            win_rate = wins / len(statuses)
            recommendation = _classify(win_rate)
            name = f"{flag}@{regime}"
            conn.execute(
                "INSERT OR REPLACE INTO patterns ("
                "name, occurrences, wins, losses, win_rate, recommendation, last_seen"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, len(statuses), wins, len(statuses) - wins,
                 win_rate, recommendation, now.isoformat()),
            )
            n_written += 1
        conn.commit()
        return n_written
    finally:
        conn.close()
