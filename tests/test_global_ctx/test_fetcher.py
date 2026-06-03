import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from crypto_predictor.global_ctx.fetcher import (
    compute_trend_pct,
    fetch_btc_dom_trend,
    fetch_dominance_snapshot,
    read_sector_history,
    write_global_for_asof,
)


def test_fetch_btc_dom_trend_returns_float(monkeypatch):
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = {
        "data": {
            "market_cap_percentage": {"btc": 52.5},
        }
    }
    fake_http = MagicMock()
    fake_http.get.return_value = fake_resp
    val = fetch_btc_dom_trend(http_client=fake_http)
    # The function reads current btc_dom; trend computation requires history,
    # so it falls back to 0 in this naive mock test. That's fine.
    assert isinstance(val, float)


def test_write_global_for_asof_round_trips(tmp_path: Path):
    cache = tmp_path / "global_cache.db"
    asof = datetime(2026, 6, 3, 6, 0, tzinfo=timezone.utc)
    write_global_for_asof(
        db=cache, timestamp=asof.isoformat(),
        btc_dom_trend_7d=0.012, eth_btc_trend_7d=-0.005,
        total_mcap_z=1.4,
        sector_btc=0.02, sector_eth=0.03,
        sector_defi=-0.01, sector_l1=0.0,
    )
    conn = sqlite3.connect(cache)
    row = conn.execute(
        "SELECT btc_dom_trend_7d FROM global_cache WHERE timestamp = ?",
        (asof.isoformat(),),
    ).fetchone()
    conn.close()
    assert abs(row[0] - 0.012) < 1e-9


def test_fetch_dominance_snapshot_extracts_btc_and_eth():
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = {
        "data": {
            "market_cap_percentage": {"btc": 52.5, "eth": 18.0},
        }
    }
    fake_http = MagicMock()
    fake_http.get.return_value = fake_resp
    dom = fetch_dominance_snapshot(http_client=fake_http)
    assert abs(dom["btc"] - 0.525) < 1e-9
    assert abs(dom["eth"] - 0.18) < 1e-9


def test_fetch_dominance_snapshot_http_error_returns_zeros():
    fake_resp = MagicMock(status_code=500)
    fake_resp.json.return_value = {}
    fake_http = MagicMock()
    fake_http.get.return_value = fake_resp
    dom = fetch_dominance_snapshot(http_client=fake_http)
    assert dom == {"btc": 0.0, "eth": 0.0}


def test_fetch_dominance_snapshot_exception_returns_zeros():
    fake_http = MagicMock()
    fake_http.get.side_effect = RuntimeError("boom")
    dom = fetch_dominance_snapshot(http_client=fake_http)
    assert dom == {"btc": 0.0, "eth": 0.0}


def test_read_sector_history_empty_db_returns_empty(tmp_path: Path):
    db = tmp_path / "nonexistent.db"
    assert read_sector_history(db, "sector_btc", lookback_days=7) == []


def test_read_sector_history_returns_ascending_within_window(tmp_path: Path):
    db = tmp_path / "global_cache.db"
    # Recent rows within 7 days — use SQLite's CURRENT_TIMESTAMP-relative offsets.
    conn = sqlite3.connect(str(db))
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS global_cache ("
        " timestamp TEXT PRIMARY KEY, btc_dom_trend_7d REAL,"
        " eth_btc_trend_7d REAL, total_mcap_z REAL,"
        " sector_btc REAL, sector_eth REAL,"
        " sector_defi REAL, sector_l1 REAL);"
    )
    # Insert with timestamps datetime('now', '-Nd') as the PK so the SQL filter matches.
    for offset, val in [("-30 days", 0.50), ("-6 days", 0.52),
                        ("-3 days", 0.53), ("-1 days", 0.55)]:
        conn.execute(
            "INSERT INTO global_cache (timestamp, sector_btc) "
            "VALUES (datetime('now', ?), ?)",
            (offset, val),
        )
    conn.commit()
    conn.close()

    rows = read_sector_history(db, "sector_btc", lookback_days=7)
    # The -30 days row should be filtered out; remaining 3 in ASC order.
    assert len(rows) == 3
    values = [v for _, v in rows]
    assert values == [0.52, 0.53, 0.55]


def test_read_sector_history_rejects_unknown_column(tmp_path: Path):
    db = tmp_path / "global_cache.db"
    with pytest.raises(ValueError):
        read_sector_history(db, "sector_btc; DROP TABLE global_cache", 7)
    with pytest.raises(ValueError):
        read_sector_history(db, "total_mcap_z", 7)


def test_compute_trend_pct_empty_history():
    assert compute_trend_pct([]) == 0.0


def test_compute_trend_pct_single_sample():
    assert compute_trend_pct([("2026-06-03T00:00:00+00:00", 0.5)]) == 0.0


def test_compute_trend_pct_normal_case():
    hist = [("a", 0.50), ("b", 0.52), ("c", 0.55)]
    # (0.55 - 0.50) / 0.50 = 0.10
    assert abs(compute_trend_pct(hist) - 0.10) < 1e-9


def test_compute_trend_pct_negative_change():
    hist = [("a", 0.55), ("b", 0.50)]
    # (0.50 - 0.55) / 0.55 ≈ -0.0909
    assert abs(compute_trend_pct(hist) - (-0.05 / 0.55)) < 1e-9


def test_compute_trend_pct_zero_denominator():
    hist = [("a", 0.0), ("b", 0.5)]
    assert compute_trend_pct(hist) == 0.0
