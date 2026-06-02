from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.scoring.regime import detect_regime, REGIME_LABELS


def _seed_btc(root: Path, daily_drift: float = 0.0,
              funding_avg: float = 0.0, n: int = 40):
    rows = []
    p = 100.0
    for i in range(n):
        p *= (1 + daily_drift)
        rows.append({
            "timestamp": 1700000000000 + i * 86400 * 1000,
            "open": p / (1 + daily_drift), "high": p * 1.01, "low": p * 0.99,
            "close": p, "volume": 1000,
        })
    write_ohlcv(root, "BTC/USDT:USDT", "1d", pd.DataFrame(rows))
    fpath = parquet_path(root, "BTC/USDT:USDT", "funding", "futures")
    fpath.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"timestamp": 1700000000000 + i * 8 * 3600 * 1000,
         "funding_rate": funding_avg + 0.00001 * ((-1) ** i)}
        for i in range(21)
    ]).to_parquet(fpath, index=False)


def test_regime_bull_when_btc_up_and_funding_positive(tmp_path: Path):
    _seed_btc(tmp_path, daily_drift=0.005, funding_avg=0.0002)
    asof = datetime.fromtimestamp(
        (1700000000000 + 40 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    regime = detect_regime(fetcher, global_mcap_trend=1.0)
    assert regime == "BULL"


def test_regime_bear_when_btc_down_and_funding_negative(tmp_path: Path):
    _seed_btc(tmp_path, daily_drift=-0.005, funding_avg=-0.0002)
    asof = datetime.fromtimestamp(
        (1700000000000 + 40 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    regime = detect_regime(fetcher, global_mcap_trend=-1.0)
    assert regime == "BEAR"


def test_regime_chop_when_mixed_signals(tmp_path: Path):
    _seed_btc(tmp_path, daily_drift=0.001, funding_avg=0.0)
    asof = datetime.fromtimestamp(
        (1700000000000 + 40 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    regime = detect_regime(fetcher, global_mcap_trend=0.0)
    assert regime == "CHOP"


def test_regime_labels_constant():
    assert REGIME_LABELS == ("BULL", "BEAR", "CHOP")
