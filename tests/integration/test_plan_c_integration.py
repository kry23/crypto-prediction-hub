"""Plan C end-to-end: scan + rank + narrate + render + (mock) deliver."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_predictor.orchestrator.run import run_full_scan
from crypto_predictor.output.markdown_report import render_daily_report
from crypto_predictor.output.telegram_summary import render_telegram_summary
from crypto_predictor.storage.predictions_db import init_db

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = REPO_ROOT / "data" / "history"
SECTOR_MAP = REPO_ROOT / "data" / "sector_map.yaml"
CALIB = REPO_ROOT / "data" / "calibration_1_5_4.json"


@pytest.mark.skipif(
    not (HISTORY_ROOT / "ohlcv" / "BTC_USDT_USDT" / "1h.parquet").exists(),
    reason="ingest not done",
)
def test_plan_c_end_to_end(tmp_path: Path):
    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
               "BNB/USDT:USDT", "XRP/USDT:USDT"]
    db = tmp_path / "predictions.db"
    init_db(db)
    mcap_ranks = {s: i + 1 for i, s in enumerate(symbols)}
    asof = datetime.now(timezone.utc)
    result = run_full_scan(
        history_root=HISTORY_ROOT,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=SECTOR_MAP,
        predictions_db=db,
        calibration_path=CALIB if CALIB.exists() else None,
        symbols=symbols, mcap_ranks=mcap_ranks,
        asof=asof, formula_version="v1.5",
        k_long=3, k_short=3, llm_client=None,
    )
    slate = result["slate"]
    assert result["scan"]["n_predictions"] > 0
    md = render_daily_report(
        asof=asof, regime=result["scan"]["regime"], slate=slate,
        n_scanned=5, n_skipped=0, rolling_metrics={},
    )
    assert isinstance(md, str)
    assert "Crypto Predictor" in md
    tg = render_telegram_summary(
        asof=asof, regime=result["scan"]["regime"], slate=slate,
    )
    assert len(tg) < 800
