"""Shared SQL helpers for the Streamlit UI pages.

Pure functions that take a `psycopg.Connection` (or any DB-API 2.0
connection with a `cursor()` context manager) and return Python
dicts/lists. No Streamlit imports here — keeps the helpers testable
in isolation.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

# Same tolerance as `crypto_predictor.output.markdown_report.CEILING_TOLERANCE`
# (semantic match with the markdown daily report).
CEILING_TOLERANCE = 1e-3


def _query_today_window() -> tuple[datetime, datetime]:
    """Return (start_utc, end_utc) covering 'today' in UTC.

    Today is defined as the UTC calendar day containing `datetime.now(UTC)`.
    End is the start of tomorrow (exclusive upper bound).
    """
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _compute_next_scan(now: datetime) -> datetime:
    """Return the next 06:00 UTC after `now`.

    If `now` is before today's 06:00 UTC, returns today's 06:00 UTC.
    Otherwise returns tomorrow's 06:00 UTC.
    """
    today_06 = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now < today_06:
        return today_06
    return today_06 + timedelta(days=1)


def _current_regime(cur) -> str:
    """Most recent regime from `regime_log` (or 'unknown')."""
    cur.execute(
        "SELECT regime FROM regime_log ORDER BY date DESC LIMIT 1"
    )
    row = cur.fetchone()
    if row is None:
        return "unknown"
    return row[0] or "unknown"


def _current_calibration_version(cur, *, mode: str, start, end) -> str:
    """Calibration version from the most recent prediction today (or 'unknown')."""
    cur.execute(
        """
        SELECT calibration_version
        FROM predictions
        WHERE mode = %s
          AND created_at >= %s
          AND created_at <  %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (mode, start, end),
    )
    row = cur.fetchone()
    if row is None:
        return "unknown"
    return row[0] or "unknown"


def _regime_ceiling(cur, *, regime: str, calibration_version: str) -> float | None:
    """Return the calibration ceiling for `regime` at `calibration_version`.

    Reads `calibration_maps.map_json` for the (version, regime) row and
    returns `max(map_json['y'])`. Returns None when the row is absent
    or the JSON shape is unexpected (which is fine — callers treat
    None as 'no ceiling configured').
    """
    if regime in ("unknown", None) or calibration_version in ("unknown", None):
        return None
    cur.execute(
        """
        SELECT map_json
        FROM calibration_maps
        WHERE version = %s AND regime = %s
        """,
        (calibration_version, regime),
    )
    row = cur.fetchone()
    if row is None:
        return None
    raw = row[0]
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return None
    ys = data.get("y") if isinstance(data, dict) else None
    if not ys:
        return None
    try:
        return float(max(ys))
    except (TypeError, ValueError):
        return None


def _count_predictions(cur, *, mode: str, start, end) -> int:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM predictions
        WHERE mode = %s
          AND created_at >= %s
          AND created_at <  %s
        """,
        (mode, start, end),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _count_wild_cards(cur, *, mode: str, start, end) -> int:
    cur.execute(
        """
        SELECT COUNT(*)
        FROM predictions
        WHERE mode = %s
          AND created_at >= %s
          AND created_at <  %s
          AND confidence_flag = 'WILD_CARD'
        """,
        (mode, start, end),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _count_ceiling_hit(
    cur, *, mode: str, start, end, ceiling: float | None
) -> int:
    """Count predictions where p_direction is within CEILING_TOLERANCE of `ceiling`.

    Returns 0 when ceiling is None (no calibration loaded).
    """
    if ceiling is None:
        return 0
    cur.execute(
        """
        SELECT COUNT(*)
        FROM predictions
        WHERE mode = %s
          AND created_at >= %s
          AND created_at <  %s
          AND ABS(p_direction - %s) < %s
        """,
        (mode, start, end, ceiling, CEILING_TOLERANCE),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


_PREDICTION_COLUMNS = (
    "id", "symbol", "p_direction", "target_value", "composite_score",
    "confidence_flag", "regime", "prediction",
)


def _rows_to_dicts(rows, columns=_PREDICTION_COLUMNS) -> list[dict]:
    """Convert tuple rows from a cursor into list[dict] with numeric uplift."""
    out: list[dict] = []
    for row in rows:
        d: dict[str, Any] = dict(zip(columns, row))
        # PG NUMERIC returns Decimal; cast known-numeric columns to float
        # for downstream pandas / arithmetic.
        for key in ("p_direction", "target_value", "composite_score"):
            if key in d and d[key] is not None:
                try:
                    d[key] = float(d[key])
                except (TypeError, ValueError):
                    pass
        out.append(d)
    return out


def _top_long(cur, *, mode: str, start, end, limit: int = 20) -> list[dict]:
    cur.execute(
        """
        SELECT id, symbol, p_direction, target_value, composite_score,
               confidence_flag, regime, prediction
        FROM predictions
        WHERE mode = %s
          AND created_at >= %s
          AND created_at <  %s
          AND prediction = 'up'
          AND (confidence_flag IS NULL OR confidence_flag <> 'WILD_CARD')
        ORDER BY composite_score DESC
        LIMIT %s
        """,
        (mode, start, end, limit),
    )
    return _rows_to_dicts(cur.fetchall())


def _top_short(cur, *, mode: str, start, end, limit: int = 20) -> list[dict]:
    cur.execute(
        """
        SELECT id, symbol, p_direction, target_value, composite_score,
               confidence_flag, regime, prediction
        FROM predictions
        WHERE mode = %s
          AND created_at >= %s
          AND created_at <  %s
          AND prediction = 'down'
          AND (confidence_flag IS NULL OR confidence_flag <> 'WILD_CARD')
        ORDER BY composite_score DESC
        LIMIT %s
        """,
        (mode, start, end, limit),
    )
    return _rows_to_dicts(cur.fetchall())


def _wild_cards(cur, *, mode: str, start, end, limit: int = 20) -> list[dict]:
    cur.execute(
        """
        SELECT id, symbol, p_direction, target_value, composite_score,
               confidence_flag, regime, prediction
        FROM predictions
        WHERE mode = %s
          AND created_at >= %s
          AND created_at <  %s
          AND confidence_flag = 'WILD_CARD'
        ORDER BY composite_score DESC
        LIMIT %s
        """,
        (mode, start, end, limit),
    )
    return _rows_to_dicts(cur.fetchall())


_ANNOTATION_COLUMNS = (
    "id", "prediction_id", "symbol", "note", "action_taken",
    "entry_price", "target_price", "stop_price", "position_size_usd",
    "created_at",
)


def _active_annotations(cur, *, limit: int = 50) -> list[dict]:
    cur.execute(
        """
        SELECT id, prediction_id, symbol, note, action_taken,
               entry_price, target_price, stop_price, position_size_usd,
               created_at
        FROM manual_annotations
        WHERE closed_at IS NULL
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    out: list[dict] = []
    for row in rows:
        d = dict(zip(_ANNOTATION_COLUMNS, row))
        for key in ("entry_price", "target_price", "stop_price",
                    "position_size_usd"):
            if d.get(key) is not None:
                try:
                    d[key] = float(d[key])
                except (TypeError, ValueError):
                    pass
        out.append(d)
    return out


def todays_slate(conn, *, mode: str = "shadow") -> dict:
    """Return the current day's slate.

    Returns dict with keys:
        regime: str (most recent regime from regime_log, or 'unknown')
        calibration_version: str (from most recent prediction today)
        mode: str (echoes the kwarg)
        n_predictions: int (count of today's predictions in this mode)
        n_wild_cards: int (subset where confidence_flag='WILD_CARD')
        n_ceiling_hit: int (predictions with p_direction within 1e-3 of
                            the regime's calibration ceiling — read from
                            calibration_maps if present, otherwise 0)
        top_long: list[dict]   (top 20 by composite_score, prediction='up')
        top_short: list[dict]  (top 20 by composite_score, prediction='down')
        wild_cards: list[dict] (confidence_flag='WILD_CARD', sorted by composite_score)
        active_annotations: list[dict]
            (manual_annotations WHERE closed_at IS NULL.
             Empty until v1.2 form ships.)
        next_scan_dt: datetime (UTC; next 06:00 UTC after now)
    """
    start, end = _query_today_window()
    now = datetime.now(timezone.utc)

    with conn.cursor() as cur:
        regime = _current_regime(cur)
        calibration_version = _current_calibration_version(
            cur, mode=mode, start=start, end=end
        )
        ceiling = _regime_ceiling(
            cur, regime=regime, calibration_version=calibration_version
        )
        n_predictions = _count_predictions(cur, mode=mode, start=start, end=end)
        n_wild_cards = _count_wild_cards(cur, mode=mode, start=start, end=end)
        n_ceiling_hit = _count_ceiling_hit(
            cur, mode=mode, start=start, end=end, ceiling=ceiling
        )
        top_long = _top_long(cur, mode=mode, start=start, end=end)
        top_short = _top_short(cur, mode=mode, start=start, end=end)
        wild_cards = _wild_cards(cur, mode=mode, start=start, end=end)
        active_annotations = _active_annotations(cur)

    return {
        "regime": regime,
        "calibration_version": calibration_version,
        "mode": mode,
        "n_predictions": n_predictions,
        "n_wild_cards": n_wild_cards,
        "n_ceiling_hit": n_ceiling_hit,
        "ceiling": ceiling,
        "top_long": top_long,
        "top_short": top_short,
        "wild_cards": wild_cards,
        "active_annotations": active_annotations,
        "next_scan_dt": _compute_next_scan(now),
    }
