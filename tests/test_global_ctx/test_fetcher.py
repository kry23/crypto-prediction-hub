from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from crypto_predictor.global_ctx.fetcher import (
    fetch_btc_dom_trend, write_global_for_asof,
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
    import sqlite3
    conn = sqlite3.connect(cache)
    row = conn.execute(
        "SELECT btc_dom_trend_7d FROM global_cache WHERE timestamp = ?",
        (asof.isoformat(),),
    ).fetchone()
    conn.close()
    assert abs(row[0] - 0.012) < 1e-9
