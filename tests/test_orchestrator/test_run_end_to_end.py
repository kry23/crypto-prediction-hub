# tests/test_orchestrator/test_run_end_to_end.py
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.orchestrator.run import run_full_scan
from crypto_predictor.storage.predictions_db import init_db as init_predictions_db


def _seed_universe(root: Path, n: int = 4):
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


def test_run_full_scan_produces_ranked_slate_and_persists(tmp_path: Path):
    history = tmp_path / "history"
    _seed_universe(history, n=4)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("l1:\n" + "\n".join(
        f"  - COIN{i}/USDT:USDT" for i in range(4)
    ) + "\n")
    db = tmp_path / "predictions.db"
    init_predictions_db(db)

    asof = datetime.fromtimestamp(
        (1700000000000 + 2400 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    result = run_full_scan(
        history_root=history,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=sector_map,
        predictions_db=db,
        calibration_path=None,
        symbols=[f"COIN{i}/USDT:USDT" for i in range(4)],
        mcap_ranks={f"COIN{i}/USDT:USDT": 1 for i in range(4)},
        asof=asof,
        formula_version="v1.5",
        k_long=2, k_short=2,
        llm_client=None,
    )

    assert result["scan"]["n_predictions"] == 4
    slate = result["slate"]
    assert hasattr(slate, "top_long")
    assert hasattr(slate, "top_short")
    assert hasattr(slate, "wild_cards")
    # Each long/short entry has rationale text
    for entry in slate.top_long + slate.top_short:
        assert "rationale" in entry
        assert isinstance(entry["rationale"], str)
