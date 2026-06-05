"""Unit tests for ``crypto_predictor.ui.claude_tools``.

All PG access is faked with ``unittest.mock.MagicMock``. File-system
helpers (calibration JSON, journal) are exercised on real ``tmp_path``
sandboxes with the module's ``PROJECT_ROOT`` constant monkey-patched.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from crypto_predictor.ui import claude_tools
from crypto_predictor.ui.claude_tools import (
    TOOL_DISPATCH,
    TOOL_SCHEMAS,
    TOOLS_NEEDING_CONN,
    query_calibration_state,
    query_completeness_breakdown,
    query_intel_hub,
    query_predictions,
    read_journal,
    run_ship_criteria_check,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mock_cursor(*, description=None, fetchall_results=None,
                  fetchone_results=None):
    """Build a mock cursor with scripted column descriptions and results."""
    cur = MagicMock()
    cur.description = description
    if fetchall_results is not None:
        cur.fetchall.side_effect = fetchall_results
    if fetchone_results is not None:
        cur.fetchone.side_effect = fetchone_results
    return cur


def _mock_conn(cursor):
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn


def _named_cols(names):
    cols = []
    for n in names:
        c = MagicMock()
        c.name = n
        cols.append(c)
    return cols


# ---------------------------------------------------------------------------
# query_predictions
# ---------------------------------------------------------------------------

def test_query_predictions_empty_returns_empty_list():
    cols = _named_cols([
        "id", "symbol", "prediction", "p_direction", "target_value",
        "composite_score", "confidence_flag", "regime", "mode", "status",
        "feature_completeness", "created_at",
    ])
    cur = _mock_cursor(description=cols, fetchall_results=[[]])
    conn = _mock_conn(cur)
    assert query_predictions(conn=conn, limit=10) == []


def test_query_predictions_applies_named_filters_to_sql():
    cols = _named_cols(["id"])
    cur = _mock_cursor(description=cols, fetchall_results=[[]])
    conn = _mock_conn(cur)
    query_predictions(
        conn=conn,
        filters={"symbol": "BTC/USDT:USDT", "status": "correct",
                  "mode": "shadow", "since": "2026-06-01T00:00:00+00:00"},
        limit=25,
    )
    sql = cur.execute.call_args[0][0]
    params = cur.execute.call_args[0][1]
    assert "symbol = %s" in sql
    assert "status = %s" in sql
    assert "mode = %s" in sql
    assert "created_at >= %s" in sql
    # 4 filter params + the trailing LIMIT param.
    assert len(params) == 5
    assert params[-1] == 25


def test_query_predictions_clamps_limit_to_max():
    cols = _named_cols(["id"])
    cur = _mock_cursor(description=cols, fetchall_results=[[]])
    conn = _mock_conn(cur)
    query_predictions(conn=conn, limit=99999)
    assert cur.execute.call_args[0][1][-1] == 500


def test_query_predictions_serializes_datetime_to_isoformat():
    cols = _named_cols(["id", "symbol", "created_at"])
    fake_row = ["abc", "BTC/USDT:USDT",
                datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)]
    cur = _mock_cursor(description=cols, fetchall_results=[[fake_row]])
    conn = _mock_conn(cur)
    out = query_predictions(conn=conn, limit=1)
    assert out[0]["created_at"] == "2026-06-05T12:00:00+00:00"


# ---------------------------------------------------------------------------
# query_completeness_breakdown
# ---------------------------------------------------------------------------

def test_completeness_breakdown_returns_hit_rates_per_bucket():
    # (completeness, n, n_correct)
    rows = [("full", 100, 65), ("degraded", 40, 22)]
    cur = _mock_cursor(fetchall_results=[rows])
    conn = _mock_conn(cur)
    out = query_completeness_breakdown(conn=conn, window_days=7,
                                          mode="shadow")
    assert out["window_days"] == 7
    assert out["mode"] == "shadow"
    assert out["by_completeness"]["full"]["n"] == 100
    assert out["by_completeness"]["full"]["hit_rate"] == 0.65
    assert out["by_completeness"]["degraded"]["hit_rate"] == 0.55


def test_completeness_breakdown_handles_empty():
    cur = _mock_cursor(fetchall_results=[[]])
    conn = _mock_conn(cur)
    out = query_completeness_breakdown(conn=conn)
    assert out["by_completeness"] == {}


# ---------------------------------------------------------------------------
# query_calibration_state
# ---------------------------------------------------------------------------

def _write_calib(tmp_path: Path, version: str, payload: dict) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    path = data_dir / f"calibration_{version}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_query_calibration_state_legacy_regimes(tmp_path, monkeypatch):
    payload = {
        "fit_window": "2026-03-27..2026-05-26",
        "regimes": {
            "BULL": {"x": [0.0, 0.5, 1.0], "y": [0.4, 0.55, 0.78]},
            "CHOP": {"x": [0.0, 1.0], "y": [0.5, 0.6]},
        },
    }
    _write_calib(tmp_path, "1_5_4", payload)
    monkeypatch.setattr(claude_tools, "PROJECT_ROOT", tmp_path)
    out = query_calibration_state(version="1_5_4")
    assert out["format"] == "legacy"
    assert set(out["keys"]) == {"BULL", "CHOP"}
    assert out["knot_counts"]["BULL"] == 3
    assert out["ceilings"]["BULL"] == 0.78
    assert out["fit_window"] == "2026-03-27..2026-05-26"


def test_query_calibration_state_missing_file_returns_error(tmp_path,
                                                              monkeypatch):
    monkeypatch.setattr(claude_tools, "PROJECT_ROOT", tmp_path)
    out = query_calibration_state(version="9_9_9")
    assert out["format"] == "missing"
    assert "not found" in out["error"]


def test_query_calibration_state_per_completeness(tmp_path, monkeypatch):
    payload = {
        "per_completeness": {
            "full": {"x": [0, 1], "y": [0.4, 0.7]},
            "degraded": {"x": [0, 1, 2], "y": [0.3, 0.5, 0.6]},
        },
    }
    _write_calib(tmp_path, "2_0_0", payload)
    monkeypatch.setattr(claude_tools, "PROJECT_ROOT", tmp_path)
    out = query_calibration_state(version="2_0_0")
    assert out["format"] == "per_completeness"
    assert out["knot_counts"]["degraded"] == 3
    assert out["ceilings"]["full"] == 0.7


# ---------------------------------------------------------------------------
# query_intel_hub
# ---------------------------------------------------------------------------

def test_query_intel_hub_marks_whale_and_news_rows():
    whale_rows = [(
        1, "ETH", "BTC", "0xdead", 1_200_000.0, "BinanceHot",
        "0xother", datetime(2026, 6, 5, 9, 0, tzinfo=timezone.utc),
    )]
    news_rows = [(
        2, "hack", "high", "Exchange X breached", "https://example",
        "newsapi", ["BTC"], 0.2,
        datetime(2026, 6, 5, 10, 0, tzinfo=timezone.utc),
    )]
    cur = _mock_cursor(fetchall_results=[whale_rows, news_rows])
    conn = _mock_conn(cur)
    out = query_intel_hub(conn=conn, category="hack", hours_back=24)
    sources = {row["source"] for row in out}
    assert sources == {"whale", "news"}
    whale = next(r for r in out if r["source"] == "whale")
    assert whale["amount_usd"] == 1_200_000.0
    assert whale["ts"].startswith("2026-06-05")


# ---------------------------------------------------------------------------
# read_journal
# ---------------------------------------------------------------------------

def test_read_journal_filters_sections_by_regex(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs" / "sessions"
    docs_dir.mkdir(parents=True)
    journal = docs_dir / "2026-06-05-full-session-journal.md"
    journal.write_text(
        "# Top header\nintro line\n\n"
        "## Task 7\nTask 7 body line one\nTask 7 body line two\n\n"
        "## Task 8\nTask 8 body\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(claude_tools, "PROJECT_ROOT", tmp_path)
    out = read_journal(section_regex=r"Task 7")
    assert "Task 7 body line one" in out
    assert "Task 8 body" not in out


def test_read_journal_returns_empty_when_no_files(tmp_path, monkeypatch):
    (tmp_path / "docs" / "sessions").mkdir(parents=True)
    monkeypatch.setattr(claude_tools, "PROJECT_ROOT", tmp_path)
    assert read_journal() == ""


# ---------------------------------------------------------------------------
# run_ship_criteria_check
# ---------------------------------------------------------------------------

def test_run_ship_criteria_check_parses_output_and_exit_code(monkeypatch,
                                                               tmp_path):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "ship_criteria_check.py").write_text("# stub", "utf-8")
    monkeypatch.setattr(claude_tools, "PROJECT_ROOT", tmp_path)

    fake_completed = subprocess.CompletedProcess(
        args=["python", "scripts/ship_criteria_check.py"],
        returncode=0,
        stdout="hit_rate=0.66 brier=0.20\n[0.60-0.65] n=30 realized=0.62\n",
        stderr="",
    )
    monkeypatch.setattr(
        claude_tools.subprocess, "run", lambda *a, **kw: fake_completed,
    )
    out = run_ship_criteria_check()
    assert out["can_ship"] is True
    assert out["exit_code"] == 0
    assert "hit_rate" in out["headline"]
    assert out["buckets"]


def test_run_ship_criteria_check_missing_script(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_tools, "PROJECT_ROOT", tmp_path)
    out = run_ship_criteria_check()
    assert out["can_ship"] is False
    assert out["exit_code"] == -1


# ---------------------------------------------------------------------------
# Tool dispatch + schema sanity
# ---------------------------------------------------------------------------

def test_tool_schemas_match_dispatch_keys():
    names_schemas = {t["name"] for t in TOOL_SCHEMAS}
    assert names_schemas == set(TOOL_DISPATCH.keys())
    # The PG-requiring set is a strict subset.
    assert TOOLS_NEEDING_CONN.issubset(set(TOOL_DISPATCH.keys()))


def test_tool_schemas_are_valid_json_schema_objects():
    for schema in TOOL_SCHEMAS:
        assert "name" in schema
        assert "description" in schema
        assert schema["input_schema"]["type"] == "object"
