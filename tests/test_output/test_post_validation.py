# tests/test_output/test_post_validation.py
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crypto_predictor.output.post_validation import (
    format_validation_telegram,
    lookback_window,
    summarize_recent_closures,
)
from crypto_predictor.storage.predictions_db import init_db


def _insert(conn, **kwargs) -> None:
    defaults = {
        "horizon_hours": 24,
        "target_value": 0.02,
        "composite_score": 0.013,
        "formula_version": "v1.5",
        "calibration_version": "v1.5.4",
        "error_margin": None,
        "evaluation": None,
        "actual_outcome": None,
        "created_at": "2026-06-02T11:30:00+00:00",
    }
    defaults.update(kwargs)
    cols = ",".join(defaults)
    placeholders = ",".join("?" for _ in defaults)
    conn.execute(f"INSERT INTO predictions ({cols}) VALUES ({placeholders})",
                  tuple(defaults.values()))


def _setup_db(tmp_path: Path) -> Path:
    db = tmp_path / "predictions.db"
    init_db(db)
    return db


def test_summary_returns_empty_when_no_closures(tmp_path: Path):
    db = _setup_db(tmp_path)
    s = summarize_recent_closures(db_path=db,
                                    since=datetime(2026, 6, 1,
                                                    tzinfo=timezone.utc))
    assert s == {"n_closed": 0}


def test_summary_ignores_pending(tmp_path: Path):
    db = _setup_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _insert(conn, id="a", symbol="BTC/USDT:USDT", prediction="up",
             p_direction=0.65, confidence_flag="NORMAL", regime="BULL",
             status="pending")
    conn.commit()
    conn.close()
    s = summarize_recent_closures(db_path=db,
                                    since=datetime(2026, 6, 1,
                                                    tzinfo=timezone.utc))
    assert s == {"n_closed": 0}


def test_summary_aggregates_closed_predictions(tmp_path: Path):
    db = _setup_db(tmp_path)
    conn = sqlite3.connect(str(db))
    validated = "2026-06-03T11:35:00+00:00"
    _insert(conn, id="a", symbol="BTC/USDT:USDT", prediction="up",
             p_direction=0.65, confidence_flag="NORMAL", regime="BULL",
             status="correct", validated_at=validated)
    _insert(conn, id="b", symbol="ETH/USDT:USDT", prediction="up",
             p_direction=0.70, confidence_flag="NORMAL", regime="BULL",
             status="incorrect", validated_at=validated)
    _insert(conn, id="c", symbol="SOL/USDT:USDT", prediction="down",
             p_direction=0.60, confidence_flag="WILD_CARD", regime="CHOP",
             status="correct", validated_at=validated)
    _insert(conn, id="d", symbol="XRP/USDT:USDT", prediction="down",
             p_direction=0.55, confidence_flag="NORMAL", regime="CHOP",
             status="correct", validated_at=validated)
    conn.commit()
    conn.close()

    s = summarize_recent_closures(
        db_path=db, since=datetime(2026, 6, 3, 0, 0, tzinfo=timezone.utc),
    )
    assert s["n_closed"] == 4
    assert s["n_correct"] == 3
    assert s["hit_rate"] == pytest.approx(0.75)
    # Brier = mean((p-y)^2) — weighted by truth labels
    # a: (0.65-1)^2 = 0.1225
    # b: (0.70-0)^2 = 0.49
    # c: (0.60-1)^2 = 0.16
    # d: (0.55-1)^2 = 0.2025
    assert s["brier"] == pytest.approx((0.1225 + 0.49 + 0.16 + 0.2025) / 4)

    assert s["by_flag"]["NORMAL"]["n"] == 3
    assert s["by_flag"]["NORMAL"]["correct"] == 2
    assert s["by_flag"]["NORMAL"]["hit_rate"] == pytest.approx(2 / 3)
    assert s["by_flag"]["WILD_CARD"]["n"] == 1
    assert s["by_flag"]["WILD_CARD"]["correct"] == 1

    assert s["by_regime"]["BULL"]["correct"] == 1
    assert s["by_regime"]["CHOP"]["correct"] == 2

    assert s["by_direction"]["up"]["correct"] == 1
    assert s["by_direction"]["down"]["correct"] == 2


def test_summary_respects_since_window(tmp_path: Path):
    db = _setup_db(tmp_path)
    conn = sqlite3.connect(str(db))
    _insert(conn, id="old", symbol="BTC/USDT:USDT", prediction="up",
             p_direction=0.65, confidence_flag="NORMAL", regime="BULL",
             status="correct",
             validated_at="2026-05-30T11:35:00+00:00")
    _insert(conn, id="new", symbol="ETH/USDT:USDT", prediction="up",
             p_direction=0.65, confidence_flag="NORMAL", regime="BULL",
             status="incorrect",
             validated_at="2026-06-03T11:35:00+00:00")
    conn.commit()
    conn.close()

    s = summarize_recent_closures(
        db_path=db, since=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
    )
    assert s["n_closed"] == 1
    assert s["n_correct"] == 0
    assert s["hit_rate"] == 0.0


def test_format_telegram_empty_when_no_closures():
    assert format_validation_telegram({"n_closed": 0}) == ""


def test_format_telegram_renders_summary_lines():
    summary = {
        "n_closed": 10, "n_correct": 7, "hit_rate": 0.7, "brier": 0.20,
        "by_flag": {"NORMAL": {"n": 8, "correct": 6, "hit_rate": 0.75},
                    "WILD_CARD": {"n": 2, "correct": 1, "hit_rate": 0.5}},
        "by_regime": {"CHOP": {"n": 10, "correct": 7, "hit_rate": 0.7}},
        "by_direction": {"up": {"n": 6, "correct": 4, "hit_rate": 0.667},
                          "down": {"n": 4, "correct": 3, "hit_rate": 0.75}},
    }
    msg = format_validation_telegram(summary)
    assert "Validation cycle complete" in msg
    assert "Closed: 10" in msg
    assert "70.0%" in msg
    assert "0.200" in msg
    assert "NORMAL: 6/8" in msg
    assert "WILD_CARD: 1/2" in msg
    assert "CHOP: 7/10" in msg
    assert "up: 4/6" in msg
    assert "down: 3/4" in msg


def test_format_telegram_shows_delta_vs_baseline():
    summary = {
        "n_closed": 5, "n_correct": 4, "hit_rate": 0.8, "brier": 0.18,
        "by_flag": {}, "by_regime": {}, "by_direction": {},
    }
    msg = format_validation_telegram(summary,
                                       backtest_brier_baseline=0.226,
                                       backtest_hit_baseline=0.625)
    assert "17.5pp" in msg  # 80 - 62.5 = 17.5
    assert "0.046" in msg  # 0.226 - 0.18 = 0.046 lower (better)


def test_lookback_window_returns_correct_delta():
    now = datetime(2026, 6, 3, 11, 30, tzinfo=timezone.utc)
    since = lookback_window(now, hours=24)
    assert since == datetime(2026, 6, 2, 11, 30, tzinfo=timezone.utc)
