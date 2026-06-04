"""Unit tests for `crypto_predictor.ui.queries.todays_slate` + helpers.

We use `unittest.mock.MagicMock` as a stand-in for a `psycopg.Connection`
so the suite stays fast and PG-free. The SQL shape is exercised
end-to-end against a live PG instance during the cutover smoke test.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

from crypto_predictor.ui.queries import (
    _compute_next_scan,
    _query_today_window,
    todays_slate,
)


# --- _compute_next_scan ----------------------------------------------------

def test_compute_next_scan_after_06_returns_tomorrow_06():
    now = datetime(2026, 6, 5, 14, 0, tzinfo=timezone.utc)
    nxt = _compute_next_scan(now)
    assert nxt == datetime(2026, 6, 6, 6, 0, tzinfo=timezone.utc)


def test_compute_next_scan_before_06_returns_today_06():
    now = datetime(2026, 6, 5, 4, 0, tzinfo=timezone.utc)
    nxt = _compute_next_scan(now)
    assert nxt == datetime(2026, 6, 5, 6, 0, tzinfo=timezone.utc)


def test_compute_next_scan_at_06_returns_tomorrow_06():
    """Boundary: when now == 06:00 UTC, the next scan is tomorrow."""
    now = datetime(2026, 6, 5, 6, 0, tzinfo=timezone.utc)
    nxt = _compute_next_scan(now)
    assert nxt == datetime(2026, 6, 6, 6, 0, tzinfo=timezone.utc)


# --- _query_today_window ---------------------------------------------------

def test_query_today_window_is_utc_day_long():
    start, end = _query_today_window()
    assert start.tzinfo is timezone.utc
    assert end.tzinfo is timezone.utc
    assert (end - start).total_seconds() == 24 * 3600
    assert start.hour == 0 and start.minute == 0 and start.second == 0


# --- todays_slate (mocked DB) ---------------------------------------------

def _mock_conn(*, fetchone_results, fetchall_results):
    """Build a MagicMock psycopg-like connection with scripted results.

    `fetchone_results` and `fetchall_results` are lists; each call to the
    corresponding cursor method consumes the next element.
    """
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone.side_effect = list(fetchone_results)
    cur.fetchall.side_effect = list(fetchall_results)
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cur


def test_todays_slate_empty_db_returns_empty_lists():
    """When the DB has no predictions today, all lists are empty + counts 0."""
    # Order of fetchone calls (see todays_slate internals):
    #   1. regime  -> None
    #   2. calibration_version  -> None
    #   3. n_predictions count  -> (0,)
    #   4. n_wild_cards count   -> (0,)
    # (No ceiling lookup because calibration_version is 'unknown', and no
    #  n_ceiling_hit query because ceiling is None.)
    conn, cur = _mock_conn(
        fetchone_results=[None, None, (0,), (0,)],
        fetchall_results=[[], [], [], []],  # top_long, top_short, wild_cards, annotations
    )

    result = todays_slate(conn, mode="shadow")

    assert result["regime"] == "unknown"
    assert result["calibration_version"] == "unknown"
    assert result["mode"] == "shadow"
    assert result["top_long"] == []
    assert result["top_short"] == []
    assert result["wild_cards"] == []
    assert result["active_annotations"] == []
    assert result["n_predictions"] == 0
    assert result["n_wild_cards"] == 0
    assert result["n_ceiling_hit"] == 0
    assert result["ceiling"] is None
    assert result["next_scan_dt"].tzinfo is timezone.utc


def test_todays_slate_populated_returns_data():
    """Populated mock returns realistic structure including ceiling-hit count."""
    # calibration_maps.map_json: y peaks at 0.7 -> ceiling = 0.7.
    map_json = json.dumps({"x": [0.0, 0.5, 1.0], "y": [0.1, 0.4, 0.7]})

    # fetchone call order in todays_slate:
    #   1. regime
    #   2. calibration_version
    #   3. ceiling lookup (calibration_maps.map_json)
    #   4. n_predictions count
    #   5. n_wild_cards count
    #   6. n_ceiling_hit count
    conn, cur = _mock_conn(
        fetchone_results=[
            ("BULL",),
            ("1_5_4",),
            (map_json,),
            (3,),
            (1,),
            (2,),
        ],
        fetchall_results=[
            # top_long
            [("p1", "BTC/USDT:USDT", 0.65, 0.02, 0.013,
              "NORMAL", "BULL", "up")],
            # top_short
            [("p2", "ETH/USDT:USDT", 0.55, -0.015, 0.011,
              "NORMAL", "BULL", "down")],
            # wild_cards
            [("p3", "DOGE/USDT:USDT", 0.7, 0.05, 0.020,
              "WILD_CARD", "BULL", "up")],
            # active_annotations (empty until v1.2)
            [],
        ],
    )

    result = todays_slate(conn, mode="shadow")

    assert result["regime"] == "BULL"
    assert result["calibration_version"] == "1_5_4"
    assert result["ceiling"] == 0.7
    assert result["n_predictions"] == 3
    assert result["n_wild_cards"] == 1
    assert result["n_ceiling_hit"] == 2
    assert len(result["top_long"]) == 1
    assert result["top_long"][0]["symbol"] == "BTC/USDT:USDT"
    # Numeric uplift: p_direction must be a float, not Decimal
    assert isinstance(result["top_long"][0]["p_direction"], float)
    assert result["top_long"][0]["p_direction"] == 0.65
    assert len(result["top_short"]) == 1
    assert result["top_short"][0]["symbol"] == "ETH/USDT:USDT"
    assert len(result["wild_cards"]) == 1
    assert result["wild_cards"][0]["confidence_flag"] == "WILD_CARD"
    assert result["active_annotations"] == []


def test_todays_slate_ceiling_skipped_when_calibration_row_missing():
    """If calibration_maps has no row for the (version, regime), ceiling is None
    and n_ceiling_hit stays 0 (no extra COUNT query fires)."""
    conn, cur = _mock_conn(
        fetchone_results=[
            ("BULL",),
            ("1_5_4",),
            None,        # calibration_maps lookup miss
            (5,),        # n_predictions
            (0,),        # n_wild_cards
            # No n_ceiling_hit fetchone — ceiling is None so the query is skipped.
        ],
        fetchall_results=[[], [], [], []],
    )

    result = todays_slate(conn, mode="shadow")
    assert result["ceiling"] is None
    assert result["n_ceiling_hit"] == 0
    assert result["n_predictions"] == 5


def test_todays_slate_active_annotations_returned_when_present():
    """The active-annotations slot is wired even though the form ships v1.2."""
    created = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    conn, cur = _mock_conn(
        fetchone_results=[None, None, (0,), (0,)],
        fetchall_results=[
            [], [], [],
            # one open annotation
            [(42, "p1", "BTC/USDT:USDT", "scalp long",
              "long", 60000.0, 62000.0, 59000.0, 1000.0, created)],
        ],
    )

    result = todays_slate(conn, mode="shadow")
    assert len(result["active_annotations"]) == 1
    ann = result["active_annotations"][0]
    assert ann["symbol"] == "BTC/USDT:USDT"
    assert ann["entry_price"] == 60000.0
    assert ann["action_taken"] == "long"
