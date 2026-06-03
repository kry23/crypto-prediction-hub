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


def detect_feature_patterns(*, predictions_db: Path, now: datetime,
                             lookback_days: int = 30,
                             min_occurrences: int = 5,
                             feature_threshold: float = 1.0) -> int:
    """Mine feature-extreme cohorts: e.g. funding_z > 2 OR funding_z < -2."""
    cutoff = (now - timedelta(days=lookback_days)).isoformat()
    conn = sqlite3.connect(str(predictions_db))
    try:
        # For each feature, group predictions where |raw_value| > threshold
        rows = conn.execute(
            "SELECT pf.feature_name, p.id, p.status, pf.raw_value "
            "FROM predictions p JOIN predictions_features pf "
            "ON p.id = pf.prediction_id "
            "WHERE p.status IN ('correct','incorrect') AND p.validated_at >= ?",
            (cutoff,),
        ).fetchall()

        cohorts: dict[tuple, list[str]] = {}
        for fname, pid, status, raw in rows:
            if raw is None:
                continue
            if abs(raw) > feature_threshold:
                key = (fname, "POS" if raw > 0 else "NEG")
                cohorts.setdefault(key, []).append(status)

        n_written = 0
        for (fname, sign), statuses in cohorts.items():
            if len(statuses) < min_occurrences:
                continue
            wins = sum(1 for s in statuses if s == "correct")
            win_rate = wins / len(statuses)
            recommendation = _classify(win_rate)
            name = f"feat:{fname}@{sign}"
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
