"""Plan B end-to-end: scoring + calibration + tiny backtest on real BTC + ETH + SOL."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crypto_predictor.backtest.runner import run_backtest

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = REPO_ROOT / "data" / "history"
SECTOR_MAP = REPO_ROOT / "data" / "sector_map.yaml"


@pytest.mark.skipif(
    not (HISTORY_ROOT / "ohlcv" / "BTC_USDT_USDT" / "1h.parquet").exists(),
    reason="ingest not done; skipping",
)
def test_tiny_backtest_runs_end_to_end(tmp_path: Path):
    end = datetime.now(timezone.utc) - timedelta(days=7)
    start = end - timedelta(days=60)
    report = tmp_path / "report.md"
    calib = tmp_path / "calib.json"

    summary = run_backtest(
        history_root=HISTORY_ROOT,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=SECTOR_MAP,
        start=start, end=end,
        train_days=21, cal_days=14, val_days=14, slide_days=7,
        sample_interval_hours=48,
        symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
        report_path=report,
        calibration_path=calib,
    )
    assert summary["n_predictions"] > 0
    assert report.exists()
    assert calib.exists()
    assert "Plan B backtest" in report.read_text(encoding="utf-8")
