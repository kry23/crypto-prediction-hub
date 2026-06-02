from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.orchestrator.daily_scan import run_daily_scan
from crypto_predictor.storage.predictions_db import init_db as init_predictions_db


def _seed(root: Path, n_symbols: int = 3):
    np.random.seed(0)
    for i in range(n_symbols):
        sym = f"FAKE{i}/USDT:USDT"
        p = 100.0
        rows = []
        for h in range(2500):
            p *= np.exp(np.random.normal(0.0, 0.005))
            rows.append({
                "timestamp": 1700000000000 + h * 3600 * 1000,
                "open": p, "high": p * 1.01, "low": p * 0.99,
                "close": p, "volume": 1000,
            })
        write_ohlcv(root, sym, "1h", pd.DataFrame(rows))
        for tf, step in [("15m", 900), ("4h", 14400), ("1d", 86400)]:
            n = max(120, 100 * (86400 // step) if step <= 86400 else 100)
            n = min(n, 8800)
            df = pd.DataFrame([
                {"timestamp": 1700000000000 + j * step * 1000, "open": 100,
                 "high": 101, "low": 99, "close": 100, "volume": 1000}
                for j in range(n)
            ])
            write_ohlcv(root, sym, tf, df)
        for kind in ["funding", "oi", "ls_ratio", "liq"]:
            p_path = parquet_path(root, sym, kind, "futures")
            p_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame().to_parquet(p_path, index=False)


def test_run_daily_scan_persists_predictions(tmp_path: Path):
    history = tmp_path / "history"
    _seed(history, n_symbols=3)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("l1:\n" + "\n".join(
        f"  - FAKE{i}/USDT:USDT" for i in range(3)
    ) + "\n")
    db = tmp_path / "predictions.db"
    init_predictions_db(db)

    asof = datetime.fromtimestamp(
        (1700000000000 + 2400 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    result = run_daily_scan(
        history_root=history,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=sector_map,
        predictions_db=db,
        calibration_path=None,  # use default 0.5 fallback
        symbols=[f"FAKE{i}/USDT:USDT" for i in range(3)],
        mcap_ranks={f"FAKE{i}/USDT:USDT": 1 for i in range(3)},
        asof=asof,
        formula_version="v1.5",
        global_mcap_trend=0.0,
    )

    assert result["n_predictions"] == 3
    assert result["regime"] in ("BULL", "BEAR", "CHOP")

    # Predictions persisted
    import sqlite3
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT symbol, prediction, p_direction, target_value, "
        "       composite_score, confidence_flag, regime, status "
        "FROM predictions"
    ).fetchall()
    conn.close()
    assert len(rows) == 3
    for row in rows:
        symbol, prediction, p_direction, target_value, composite, flag, regime, status = row
        assert prediction in ("up", "down")
        assert 0.0 <= p_direction <= 1.0
        assert flag in ("NORMAL", "HIGH_CONV", "WILD_CARD")
        assert status == "pending"
