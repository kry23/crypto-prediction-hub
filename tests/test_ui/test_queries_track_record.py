"""Unit tests for the track-record helpers in `crypto_predictor.ui.queries`.

Covers:
    - rolling_kpis
    - per_bucket_calibration
    - daily_hit_rates
    - by_regime_and_flag

Same mock-based style as `test_queries_dashboard.py`: a MagicMock stands in
for `psycopg.Connection` so the suite stays fast and PG-free. The SQL
shape is exercised end-to-end against a live PG instance during the
cutover smoke test.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from crypto_predictor.ui.queries import (
    by_regime_and_flag,
    daily_hit_rates,
    per_bucket_calibration,
    rolling_kpis,
)


def _mock_cur(conn: MagicMock) -> MagicMock:
    """Wire conn.cursor() to behave as a context manager yielding a fresh cur."""
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    return cur


# --- rolling_kpis ---------------------------------------------------------

def test_rolling_kpis_empty_window_returns_zeros():
    conn = MagicMock()
    cur = _mock_cur(conn)
    # closed-rows fetchall returns empty.
    cur.fetchall.return_value = []
    # five COUNT(*) fetchones: n_total, n_pending, n_correct, n_incorrect, n_expired.
    cur.fetchone.side_effect = [(0,), (0,), (0,), (0,), (0,)]

    out = rolling_kpis(conn, window_days=7, mode="shadow")

    assert out["n_total"] == 0
    assert out["n_pending"] == 0
    assert out["n_correct"] == 0
    assert out["n_incorrect"] == 0
    assert out["n_expired"] == 0
    assert out["n_closed"] == 0
    assert out["hit_rate"] == 0.0
    assert out["brier"] == 0.0


def test_rolling_kpis_computes_brier_correctly():
    """Brier = mean((p - y)^2) where y=1 for correct, 0 for incorrect."""
    conn = MagicMock()
    cur = _mock_cur(conn)
    # (status, p_direction) — 1 correct @0.6, 1 incorrect @0.7.
    # Brier = ((0.6-1)^2 + (0.7-0)^2) / 2 = (0.16 + 0.49) / 2 = 0.325
    cur.fetchall.return_value = [
        ("correct", 0.6),
        ("incorrect", 0.7),
    ]
    cur.fetchone.side_effect = [(2,), (0,), (1,), (1,), (0,)]

    out = rolling_kpis(conn, window_days=7, mode="shadow")

    expected_brier = (0.16 + 0.49) / 2
    assert abs(out["brier"] - expected_brier) < 1e-6
    assert abs(out["hit_rate"] - 0.5) < 1e-6
    assert out["n_closed"] == 2
    assert out["n_total"] == 2
    assert out["n_correct"] == 1
    assert out["n_incorrect"] == 1


# --- per_bucket_calibration -----------------------------------------------

def test_per_bucket_calibration_returns_buckets():
    """Per-bucket realized stats over mocked rows; well-populated buckets
    return soft_pass=False with a real delta_pp."""
    conn = MagicMock()
    cur = _mock_cur(conn)
    # 25 rows all in [0.60, 0.65) at p=0.62, 12 correct.
    rows = [
        ("correct" if i < 12 else "incorrect", 0.62)
        for i in range(25)
    ]
    cur.fetchall.return_value = rows

    out = per_bucket_calibration(
        conn, window_days=7, min_samples_per_bucket=20,
    )

    bucket = next(
        (b for b in out if b["lo"] == 0.60 and b["hi"] == 0.65),
        None,
    )
    assert bucket is not None
    assert bucket["n"] == 25
    assert bucket["soft_pass"] is False
    assert abs(bucket["realized"] - 12 / 25) < 1e-9
    assert abs(bucket["expected"] - 0.62) < 1e-9


def test_per_bucket_calibration_soft_pass_below_threshold():
    """Sparse buckets soft-pass with delta_pp=0 (rendered but not held to
    the 10pp tolerance)."""
    conn = MagicMock()
    cur = _mock_cur(conn)
    # 5 rows all in [0.80, 0.95).
    rows = [("correct", 0.85) for _ in range(5)]
    cur.fetchall.return_value = rows

    out = per_bucket_calibration(
        conn, window_days=7, min_samples_per_bucket=20,
    )

    bucket = next(
        (b for b in out if b["lo"] == 0.80 and b["hi"] == 0.95),
        None,
    )
    assert bucket is not None
    assert bucket["n"] == 5
    assert bucket["soft_pass"] is True
    assert bucket["delta_pp"] == 0.0


def test_per_bucket_calibration_empty_buckets_omitted():
    """Buckets with zero samples must not appear in the output."""
    conn = MagicMock()
    cur = _mock_cur(conn)
    cur.fetchall.return_value = []

    out = per_bucket_calibration(
        conn, window_days=7, min_samples_per_bucket=20,
    )

    assert out == []


# --- daily_hit_rates -------------------------------------------------------

def test_daily_hit_rates_aggregates_per_day():
    conn = MagicMock()
    cur = _mock_cur(conn)
    cur.fetchall.return_value = [
        ("2026-06-04", 10, 14),
        ("2026-06-05", 7, 12),
    ]

    out = daily_hit_rates(conn, window_days=7, mode="shadow")

    assert len(out) == 2
    assert out[0]["date"] == "2026-06-04"
    assert abs(out[0]["hit_rate"] - 10 / 14) < 1e-6
    assert out[0]["n"] == 14
    assert out[1]["date"] == "2026-06-05"
    assert out[1]["n"] == 12


def test_daily_hit_rates_empty_returns_empty_list():
    conn = MagicMock()
    cur = _mock_cur(conn)
    cur.fetchall.return_value = []

    out = daily_hit_rates(conn, window_days=14, mode="shadow")

    assert out == []


# --- by_regime_and_flag ----------------------------------------------------

def test_by_regime_and_flag_returns_breakdown():
    conn = MagicMock()
    cur = _mock_cur(conn)
    cur.fetchall.return_value = [
        ("BULL", "NORMAL", 100, 65),
        ("CHOP", "WILD_CARD", 10, 3),
    ]

    out = by_regime_and_flag(conn, window_days=7, mode="shadow")

    assert len(out) == 2
    assert out[0]["regime"] == "BULL"
    assert out[0]["flag"] == "NORMAL"
    assert out[0]["n"] == 100
    assert out[0]["correct"] == 65
    assert abs(out[0]["hit_rate"] - 0.65) < 1e-6
    assert out[1]["regime"] == "CHOP"
    assert out[1]["flag"] == "WILD_CARD"
    assert abs(out[1]["hit_rate"] - 0.3) < 1e-6


def test_by_regime_and_flag_empty_returns_empty_list():
    conn = MagicMock()
    cur = _mock_cur(conn)
    cur.fetchall.return_value = []

    out = by_regime_and_flag(conn, window_days=7, mode="shadow")

    assert out == []
