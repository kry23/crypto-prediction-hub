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


# --- Fast-downtrend override (remedy A) -------------------------------------
# The 30d-BTC vote lags a sharp selloff, leaving a downtrend classified CHOP —
# where mean-reversion longs the falling knives (observed 2026-06 shadow). A
# sharp 7d drop is a downtrend; classify BEAR even when the 30d hasn't flipped.

def _seed_btc_closes(root: Path, closes: list[float],
                     funding_avg: float = 0.0):
    """Seed BTC daily OHLCV from an explicit close path (+ near-flat funding)."""
    rows = [
        {"timestamp": 1700000000000 + i * 86400 * 1000,
         "open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1000}
        for i, c in enumerate(closes)
    ]
    write_ohlcv(root, "BTC/USDT:USDT", "1d", pd.DataFrame(rows))
    fpath = parquet_path(root, "BTC/USDT:USDT", "funding", "futures")
    fpath.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"timestamp": 1700000000000 + i * 8 * 3600 * 1000,
         "funding_rate": funding_avg + 0.00001 * ((-1) ** i)}
        for i in range(21)
    ]).to_parquet(fpath, index=False)


def _asof(n_bars: int) -> datetime:
    return datetime.fromtimestamp(
        (1700000000000 + n_bars * 86400 * 1000) / 1000, tz=timezone.utc
    )


def test_fast_downtrend_overrides_chop_to_bear(tmp_path: Path):
    # Rise to 115 then a sharp 7d drop to ~102: 30d ~ +1% (no vote), 7d ~ -12%.
    rise = [100 + (15 * i / 24) for i in range(25)]      # idx 0..24 -> 115
    fall = [115 - (13 * j / 7) for j in range(1, 8)]     # idx 25..31 -> ~102
    _seed_btc_closes(tmp_path, rise + fall, funding_avg=0.0)
    fetcher = FeatureFetcher(root=tmp_path, asof=_asof(32))
    assert detect_regime(fetcher, global_mcap_trend=0.0) == "BEAR"


def test_mild_recent_dip_stays_chop(tmp_path: Path):
    # Flat then a small 7d dip (~-3.5%): 30d ~ flat, 7d above threshold -> CHOP.
    closes = [100.0] * 25 + [100 - 0.5 * j for j in range(1, 8)]
    _seed_btc_closes(tmp_path, closes, funding_avg=0.0)
    fetcher = FeatureFetcher(root=tmp_path, asof=_asof(32))
    assert detect_regime(fetcher, global_mcap_trend=0.0) == "CHOP"


def test_strong_bull_with_correction_stays_bull(tmp_path: Path):
    # Net 30d bull (+12%) + positive funding + positive mcap = 3 bull votes,
    # so a sharp 7d correction must NOT override a genuine bull.
    rise = [100 + (40 * i / 24) for i in range(25)]      # -> 140
    fall = [140 - (25 * j / 7) for j in range(1, 8)]     # -> 115
    _seed_btc_closes(tmp_path, rise + fall, funding_avg=0.0002)
    fetcher = FeatureFetcher(root=tmp_path, asof=_asof(32))
    assert detect_regime(fetcher, global_mcap_trend=1.0) == "BULL"


def test_fast_downtrend_threshold_constant():
    from crypto_predictor.scoring.regime import FAST_DOWNTREND_THRESHOLD
    assert FAST_DOWNTREND_THRESHOLD < 0
