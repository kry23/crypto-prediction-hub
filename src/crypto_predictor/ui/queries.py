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


# --- Track Record helpers --------------------------------------------------
#
# These power the Track Record page (Task 5). All four return plain dicts
# / lists so they can be pandas-DataFrame-ified in the page layer without
# any DB coupling. The shapes mirror `scripts/ship_criteria_check.py` so
# the page can render the same numbers the ship-criteria check produces.

# Bucket boundaries match `scripts/ship_criteria_check.BUCKETS`.
_CALIBRATION_BUCKETS = [
    (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70),
    (0.70, 0.75), (0.75, 0.80), (0.80, 0.95),
]


def rolling_kpis(conn, *, window_days: int = 7,
                 mode: str = "shadow") -> dict:
    """Return aggregate KPIs over the last ``window_days`` of predictions
    for the given mode.

    Returns dict with keys:
        n_total, n_pending, n_correct, n_incorrect, n_expired,
        n_closed, hit_rate (float in [0,1]), brier (float).

    When no closed predictions are in-window, hit_rate and brier are 0.0.
    Brier is computed in Python as ``mean((p_direction - y)^2)`` where
    y=1 for correct, y=0 for incorrect.
    """
    with conn.cursor() as cur:
        # Pull (status, p_direction) for closed rows to compute Brier+hit-rate.
        cur.execute(
            """
            SELECT status, p_direction
            FROM predictions
            WHERE mode = %s
              AND status IN ('correct','incorrect')
              AND validated_at >= (now() AT TIME ZONE 'UTC')
                                   - make_interval(days => %s)
            """,
            (mode, window_days),
        )
        closed_rows = cur.fetchall()

        # Counts by status (over the same window).
        cur.execute(
            """
            SELECT COUNT(*)
            FROM predictions
            WHERE mode = %s
              AND created_at >= (now() AT TIME ZONE 'UTC')
                                  - make_interval(days => %s)
            """,
            (mode, window_days),
        )
        row = cur.fetchone()
        n_total = int(row[0]) if row and row[0] is not None else 0

        cur.execute(
            """
            SELECT COUNT(*)
            FROM predictions
            WHERE mode = %s
              AND status = 'pending'
              AND created_at >= (now() AT TIME ZONE 'UTC')
                                  - make_interval(days => %s)
            """,
            (mode, window_days),
        )
        row = cur.fetchone()
        n_pending = int(row[0]) if row and row[0] is not None else 0

        cur.execute(
            """
            SELECT COUNT(*)
            FROM predictions
            WHERE mode = %s
              AND status = 'correct'
              AND validated_at >= (now() AT TIME ZONE 'UTC')
                                   - make_interval(days => %s)
            """,
            (mode, window_days),
        )
        row = cur.fetchone()
        n_correct = int(row[0]) if row and row[0] is not None else 0

        cur.execute(
            """
            SELECT COUNT(*)
            FROM predictions
            WHERE mode = %s
              AND status = 'incorrect'
              AND validated_at >= (now() AT TIME ZONE 'UTC')
                                   - make_interval(days => %s)
            """,
            (mode, window_days),
        )
        row = cur.fetchone()
        n_incorrect = int(row[0]) if row and row[0] is not None else 0

        cur.execute(
            """
            SELECT COUNT(*)
            FROM predictions
            WHERE mode = %s
              AND status = 'expired'
              AND validated_at >= (now() AT TIME ZONE 'UTC')
                                   - make_interval(days => %s)
            """,
            (mode, window_days),
        )
        row = cur.fetchone()
        n_expired = int(row[0]) if row and row[0] is not None else 0

    n_closed = len(closed_rows)
    if n_closed == 0:
        hit_rate = 0.0
        brier = 0.0
    else:
        correct = sum(1 for status, _ in closed_rows if status == "correct")
        hit_rate = correct / n_closed
        squared_errors = []
        for status, p_dir in closed_rows:
            try:
                p = float(p_dir)
            except (TypeError, ValueError):
                continue
            y = 1.0 if status == "correct" else 0.0
            squared_errors.append((p - y) ** 2)
        brier = (sum(squared_errors) / len(squared_errors)
                 if squared_errors else 0.0)

    return {
        "n_total": n_total,
        "n_pending": n_pending,
        "n_correct": n_correct,
        "n_incorrect": n_incorrect,
        "n_expired": n_expired,
        "n_closed": n_closed,
        "hit_rate": hit_rate,
        "brier": brier,
    }


def per_bucket_calibration(conn, *, window_days: int = 7,
                           mode: str = "shadow",
                           min_samples_per_bucket: int = 20) -> list[dict]:
    """Per-p-bucket realized-vs-expected stats over the rolling window.

    Mirrors `scripts/ship_criteria_check.check_bucket_bar` so the page
    shows the same numbers as the CLI check. Returns a list of dicts
    with keys: lo, hi, n, realized, expected, delta_pp, soft_pass.

    Sparse buckets (``n < min_samples_per_bucket``) are returned with
    ``soft_pass=True`` and ``delta_pp=0.0``. Empty buckets are omitted.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, p_direction
            FROM predictions
            WHERE mode = %s
              AND status IN ('correct','incorrect')
              AND validated_at >= (now() AT TIME ZONE 'UTC')
                                   - make_interval(days => %s)
            """,
            (mode, window_days),
        )
        rows = cur.fetchall()

    # Pre-cast to (status, float p) once.
    closed: list[tuple[str, float]] = []
    for status, p_dir in rows:
        try:
            closed.append((status, float(p_dir)))
        except (TypeError, ValueError):
            continue

    out: list[dict] = []
    for lo, hi in _CALIBRATION_BUCKETS:
        sub = [(s, p) for (s, p) in closed if lo <= p < hi]
        n = len(sub)
        if n == 0:
            continue
        realized = sum(1 for s, _ in sub if s == "correct") / n
        expected = sum(p for _, p in sub) / n
        if n < min_samples_per_bucket:
            out.append({
                "lo": lo, "hi": hi, "n": n,
                "realized": float(realized),
                "expected": float(expected),
                "delta_pp": 0.0,
                "soft_pass": True,
            })
            continue
        delta_pp = abs(realized - expected) * 100
        out.append({
            "lo": lo, "hi": hi, "n": n,
            "realized": float(realized),
            "expected": float(expected),
            "delta_pp": float(delta_pp),
            "soft_pass": False,
        })
    return out


def daily_hit_rates(conn, *, window_days: int = 14,
                    mode: str = "shadow") -> list[dict]:
    """Per-day hit-rate trend over the last ``window_days``.

    Returns a list of dicts: ``{date: 'YYYY-MM-DD', n: int, hit_rate: float}``,
    ordered oldest -> newest. Days with no closures are omitted (the page
    layer renders gaps as gaps).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT date(validated_at) AS day,
                   SUM(CASE WHEN status = 'correct' THEN 1 ELSE 0 END) AS hits,
                   COUNT(*) AS n
            FROM predictions
            WHERE mode = %s
              AND status IN ('correct','incorrect')
              AND validated_at >= (now() AT TIME ZONE 'UTC')
                                   - make_interval(days => %s)
            GROUP BY date(validated_at)
            ORDER BY date(validated_at)
            """,
            (mode, window_days),
        )
        rows = cur.fetchall()

    out: list[dict] = []
    for day, hits, n in rows:
        if hasattr(day, "isoformat"):
            day_str = day.isoformat()
        else:
            day_str = str(day)
        n_int = int(n) if n is not None else 0
        hits_int = int(hits) if hits is not None else 0
        hit_rate = hits_int / n_int if n_int else 0.0
        out.append({"date": day_str, "n": n_int, "hit_rate": hit_rate})
    return out


def by_regime_and_flag(conn, *, window_days: int = 7,
                       mode: str = "shadow") -> list[dict]:
    """Breakdown of closed predictions by ``(regime, confidence_flag)``.

    Returns a list of dicts with keys: regime, flag, n, correct, hit_rate.
    Sorted by n descending so the busiest cells render first.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT regime,
                   confidence_flag,
                   COUNT(*) AS n,
                   SUM(CASE WHEN status = 'correct' THEN 1 ELSE 0 END) AS correct
            FROM predictions
            WHERE mode = %s
              AND status IN ('correct','incorrect')
              AND validated_at >= (now() AT TIME ZONE 'UTC')
                                   - make_interval(days => %s)
            GROUP BY regime, confidence_flag
            ORDER BY COUNT(*) DESC
            """,
            (mode, window_days),
        )
        rows = cur.fetchall()

    out: list[dict] = []
    for regime, flag, n, correct in rows:
        n_int = int(n) if n is not None else 0
        correct_int = int(correct) if correct is not None else 0
        hit_rate = correct_int / n_int if n_int else 0.0
        out.append({
            "regime": regime,
            "flag": flag,
            "n": n_int,
            "correct": correct_int,
            "hit_rate": hit_rate,
        })
    return out
