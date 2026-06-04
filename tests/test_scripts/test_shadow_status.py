# tests/test_scripts/test_shadow_status.py
from pathlib import Path

from scripts.shadow_status import summarize, render


def _row(**kw):
    base = {
        "id": "x", "symbol": "BTC/USDT:USDT", "status": "pending",
        "p_direction": 0.6, "target_value": 0.01,
        "confidence_flag": "NORMAL", "regime": "CHOP",
        "feature_completeness": "full", "missing_features": None,
        "calibration_version": "1_5_4",
        "created_at": "2026-06-04T06:00:00+00:00",
    }
    base.update(kw)
    return base


def test_summarize_empty_returns_zero():
    s = summarize([])
    assert s["n_total"] == 0


def test_summarize_counts_status_breakdown():
    rows = [
        _row(id="1", status="pending"),
        _row(id="2", status="correct"),
        _row(id="3", status="incorrect"),
        _row(id="4", status="expired"),
    ]
    s = summarize(rows)
    assert s["n_total"] == 4
    assert s["n_pending"] == 1
    assert s["n_correct"] == 1
    assert s["n_incorrect"] == 1
    assert s["n_expired"] == 1
    assert s["n_closed"] == 2  # correct + incorrect
    assert s["hit_rate"] == 0.5


def test_summarize_completeness_and_regime_buckets():
    rows = [
        _row(id="a", feature_completeness="full", regime="BULL"),
        _row(id="b", feature_completeness="degraded", regime="CHOP"),
        _row(id="c", feature_completeness="full", regime="CHOP"),
    ]
    s = summarize(rows)
    assert s["completeness_counts"] == {"full": 2, "degraded": 1}
    assert s["regime_counts"] == {"BULL": 1, "CHOP": 2}


def test_summarize_date_range_and_day_count():
    rows = [
        _row(id="1", created_at="2026-06-04T06:00:00+00:00"),
        _row(id="2", created_at="2026-06-05T06:00:00+00:00"),
        _row(id="3", created_at="2026-06-05T07:00:00+00:00"),
    ]
    s = summarize(rows)
    assert s["date_range"] == ("2026-06-04", "2026-06-05")
    assert s["n_days"] == 2


def test_render_includes_ready_message_at_target_days():
    summary = {
        "n_total": 4800, "n_pending": 200, "n_correct": 2000,
        "n_incorrect": 1500, "n_expired": 1100, "n_closed": 3500,
        "hit_rate": 0.571,
        "completeness_counts": {"full": 4800},
        "regime_counts": {"CHOP": 4800},
        "calibration_versions": {"1_5_4": 4800},
        "date_range": ("2026-06-04", "2026-06-17"),
        "n_days": 14,
    }
    msg = render(summary)
    assert "ready to execute" in msg
    assert "57.1%" in msg


def test_render_includes_target_progress_below_threshold():
    summary = {
        "n_total": 342, "n_pending": 342, "n_correct": 0,
        "n_incorrect": 0, "n_expired": 0, "n_closed": 0,
        "hit_rate": 0.0,
        "completeness_counts": {"full": 342},
        "regime_counts": {"CHOP": 342},
        "calibration_versions": {"1_5_4": 342},
        "date_range": ("2026-06-04", "2026-06-04"),
        "n_days": 1,
    }
    msg = render(summary)
    assert "1/14" in msg


def test_render_empty_returns_no_data_message():
    msg = render({"n_total": 0})
    assert "No shadow predictions yet" in msg
