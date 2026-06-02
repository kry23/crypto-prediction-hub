"""End-to-end Plan A integration test — real parquet, compute full feature dict."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_predictor.features.compute import compute_features
from crypto_predictor.features.fetcher import FeatureFetcher

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = REPO_ROOT / "data" / "history"
SECTOR_MAP = REPO_ROOT / "data" / "sector_map.yaml"

# The ingest used ccxt unified symbols; the parquet store sanitized them.
# We call compute_features with the unified symbol because that's what the
# live orchestrator will pass (Week 7 daily run).
BTC_SYMBOL_UNIFIED = "BTC/USDT:USDT"


@pytest.mark.skipif(
    not (HISTORY_ROOT / "ohlcv" / "BTC_USDT_USDT" / "1h.parquet").exists(),
    reason="bulk ingest (Task 2.7) has not completed; skipping integration test",
)
def test_full_feature_dict_for_btc_real_data():
    asof = datetime.now(timezone.utc)
    fetcher = FeatureFetcher(root=HISTORY_ROOT, asof=asof)
    feats = compute_features(
        fetcher=fetcher,
        symbol=BTC_SYMBOL_UNIFIED,
        sentiment_cache=HISTORY_ROOT.parent / "sentiment_cache.db",
        global_cache=HISTORY_ROOT.parent / "global_cache.db",
        sector_map_path=SECTOR_MAP,
        mcap_rank=1,
    )
    assert len(feats) >= 25, f"expected >=25 features, got {len(feats)}: {list(feats.keys())}"
    # Spot-check: all values numeric, no NaN
    import math
    for k, v in feats.items():
        assert isinstance(v, (int, float)), f"{k} is {type(v).__name__}"
        assert not math.isnan(v), f"{k} is NaN"
