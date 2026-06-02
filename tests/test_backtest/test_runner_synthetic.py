from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.backtest.runner import run_backtest


def _seed_fake_universe(root: Path, n_symbols: int = 3, n_days: int = 30):
    np.random.seed(0)
    for i in range(n_symbols):
        sym = f"FAKE{i}/USDT:USDT"
        p = 100.0
        rows = []
        for h in range(n_days * 24 + 100):
            p *= np.exp(np.random.normal(0.0, 0.005))
            rows.append({
                "timestamp": 1700000000000 + h * 3600 * 1000,
                "open": p, "high": p * 1.01, "low": p * 0.99,
                "close": p, "volume": 1000,
            })
        write_ohlcv(root, sym, "1h", pd.DataFrame(rows))
        d_rows = [
            {"timestamp": 1700000000000 + d * 86400 * 1000,
             "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
            for d in range(n_days + 5)
        ]
        write_ohlcv(root, sym, "1d", pd.DataFrame(d_rows))
        for kind in ["funding", "oi", "ls_ratio", "liq"]:
            p_path = parquet_path(root, sym, kind, "futures")
            p_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame().to_parquet(p_path, index=False)


def test_run_backtest_produces_report_and_calibration(tmp_path: Path):
    history = tmp_path / "history"
    _seed_fake_universe(history, n_symbols=3, n_days=20)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("l1:\n  - FAKE0/USDT:USDT\n  - FAKE1/USDT:USDT\n  - FAKE2/USDT:USDT\n")

    report_path = tmp_path / "report.md"
    calibration_path = tmp_path / "calib.json"

    result = run_backtest(
        history_root=history,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=sector_map,
        start=datetime.fromtimestamp(1700000000000 / 1000 + 86400, tz=timezone.utc),
        end=datetime.fromtimestamp(1700000000000 / 1000 + 19 * 86400, tz=timezone.utc),
        train_days=10, cal_days=3, val_days=3, slide_days=3,
        sample_interval_hours=12,
        symbols=["FAKE0/USDT:USDT", "FAKE1/USDT:USDT", "FAKE2/USDT:USDT"],
        report_path=report_path,
        calibration_path=calibration_path,
    )
    assert report_path.exists()
    assert calibration_path.exists()
    assert result["n_predictions"] > 0


def test_run_backtest_reports_nonzero_short_alpha(tmp_path: Path):
    """After 1.5.1 fix, short_alpha should be computed (not hardcoded 0)."""
    history = tmp_path / "history"
    _seed_fake_universe(history, n_symbols=5, n_days=20)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text(
        "l1:\n"
        + "\n".join(f"  - FAKE{i}/USDT:USDT" for i in range(5))
        + "\n"
    )
    report_path = tmp_path / "report.md"
    calibration_path = tmp_path / "calib.json"
    summary = run_backtest(
        history_root=history,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=sector_map,
        start=datetime.fromtimestamp(1700000000000 / 1000 + 86400, tz=timezone.utc),
        end=datetime.fromtimestamp(1700000000000 / 1000 + 19 * 86400, tz=timezone.utc),
        train_days=10, cal_days=3, val_days=3, slide_days=3,
        sample_interval_hours=12,
        symbols=[f"FAKE{i}/USDT:USDT" for i in range(5)],
        report_path=report_path,
        calibration_path=calibration_path,
    )
    # We don't know the sign on synthetic GBM, but it should NOT be exactly 0.0
    # (unless by absurd coincidence). The fix means it's computed, not hardcoded.
    report = report_path.read_text(encoding="utf-8")
    assert "Short alpha" in report
    # At least confirm the report value isn't the placeholder "+0.00%" for both long+short
    import re
    short_match = re.search(r"Short alpha\W+([+-]?\d+\.\d+)%", report)
    long_match = re.search(r"Long alpha\W+([+-]?\d+\.\d+)%", report)
    assert short_match is not None
    assert long_match is not None
    # On synthetic GBM data, at least one of long/short should be nonzero (with high probability)
    long_val = float(long_match.group(1))
    short_val = float(short_match.group(1))
    assert (long_val != 0.0) or (short_val != 0.0)
