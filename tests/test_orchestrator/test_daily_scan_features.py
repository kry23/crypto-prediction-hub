import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from tests.test_orchestrator.test_daily_scan_synthetic import _seed
from crypto_predictor.orchestrator.daily_scan import run_daily_scan
from crypto_predictor.storage.predictions_db import init_db


def test_predictions_features_populated(tmp_path: Path):
    _seed(tmp_path, n_symbols=2)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("l1:\n  - FAKE0/USDT:USDT\n  - FAKE1/USDT:USDT\n")
    db = tmp_path / "predictions.db"
    init_db(db)
    asof = datetime.fromtimestamp(
        (1700000000000 + 2400 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    run_daily_scan(
        history_root=tmp_path,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=sector_map,
        predictions_db=db,
        calibration_path=None,
        symbols=["FAKE0/USDT:USDT", "FAKE1/USDT:USDT"],
        mcap_ranks={"FAKE0/USDT:USDT": 1, "FAKE1/USDT:USDT": 2},
        asof=asof,
        formula_version="v1.5",
    )
    conn = sqlite3.connect(db)
    n_features = conn.execute(
        "SELECT COUNT(*) FROM predictions_features"
    ).fetchone()[0]
    n_predictions = conn.execute(
        "SELECT COUNT(*) FROM predictions"
    ).fetchone()[0]
    conn.close()
    # Expect ~30 feature rows per prediction
    assert n_features > n_predictions * 20
