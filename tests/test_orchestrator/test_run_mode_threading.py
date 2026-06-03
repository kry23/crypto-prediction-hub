# tests/test_orchestrator/test_run_mode_threading.py
"""Verify run_full_scan threads v0.2.1 mode + calibration_version kwargs."""
import inspect
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.orchestrator.run import run_full_scan
from crypto_predictor.storage.predictions_db import init_db as init_predictions_db


def test_run_full_scan_accepts_mode_kwarg():
    sig = inspect.signature(run_full_scan)
    assert "mode" in sig.parameters
    default = sig.parameters["mode"].default
    assert default == "live"  # default preserves backwards compat


def test_run_full_scan_accepts_calibration_version_kwarg():
    sig = inspect.signature(run_full_scan)
    assert "calibration_version" in sig.parameters


def _seed_universe(root: Path, n: int = 2):
    np.random.seed(1)
    for i in range(n):
        sym = f"COIN{i}/USDT:USDT"
        p = 100.0
        rows = []
        for h in range(2500):
            p *= np.exp(np.random.normal(0.0, 0.005))
            rows.append({"timestamp": 1700000000000 + h * 3600 * 1000,
                         "open": p, "high": p * 1.01, "low": p * 0.99,
                         "close": p, "volume": 1000})
        write_ohlcv(root, sym, "1h", pd.DataFrame(rows))
        for tf, step in [("15m", 900), ("4h", 14400), ("1d", 86400)]:
            n_bars = max(120, 100 * (86400 // step) if step <= 86400 else 100)
            n_bars = min(n_bars, 8800)
            df = pd.DataFrame([
                {"timestamp": 1700000000000 + j * step * 1000, "open": 100,
                 "high": 101, "low": 99, "close": 100, "volume": 1000}
                for j in range(n_bars)
            ])
            write_ohlcv(root, sym, tf, df)
        for kind in ["funding", "oi", "ls_ratio", "liq"]:
            p_path = parquet_path(root, sym, kind, "futures")
            p_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame().to_parquet(p_path, index=False)


def test_run_full_scan_persists_shadow_mode_and_degraded_completeness(
    tmp_path: Path,
):
    """Integration smoke: when caches are absent and mode='shadow',
    persisted rows record mode='shadow' and feature_completeness='degraded'."""
    history = tmp_path / "history"
    _seed_universe(history, n=2)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("l1:\n" + "\n".join(
        f"  - COIN{i}/USDT:USDT" for i in range(2)
    ) + "\n")
    db = tmp_path / "predictions.db"
    init_predictions_db(db)

    asof = datetime.fromtimestamp(
        (1700000000000 + 2400 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    # Sentiment + global caches intentionally missing -> degraded
    run_full_scan(
        history_root=history,
        sentiment_cache=tmp_path / "absent_sentiment.db",
        global_cache=tmp_path / "absent_global.db",
        sector_map=sector_map,
        predictions_db=db,
        calibration_path=None,
        symbols=[f"COIN{i}/USDT:USDT" for i in range(2)],
        mcap_ranks={f"COIN{i}/USDT:USDT": 1 for i in range(2)},
        asof=asof,
        formula_version="v1.5",
        k_long=1, k_short=1,
        llm_client=None,
        mode="shadow",
        calibration_version="1_5_4",
    )

    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT mode, feature_completeness, missing_features FROM predictions"
    ).fetchall()
    conn.close()
    assert len(rows) >= 1
    for mode, completeness, missing in rows:
        assert mode == "shadow"
        assert completeness == "degraded"
        assert missing == "sentiment,global"
