"""compute_features() — orchestrate all 6 families into one dict per coin."""
from __future__ import annotations

from pathlib import Path

from crypto_predictor.features.families.global_ctx import compute_global_features
from crypto_predictor.features.families.momentum import compute_momentum_features
from crypto_predictor.features.families.perp import compute_perp_features
from crypto_predictor.features.families.sentiment import compute_sentiment_features
from crypto_predictor.features.families.technical import compute_technical_features
from crypto_predictor.features.families.volume import compute_volume_features
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.features.mcap_weight import mcap_rank_weight
from crypto_predictor.features.sector_map import classify_sector


def compute_features(*, fetcher: FeatureFetcher, symbol: str,
                     sentiment_cache: Path, global_cache: Path,
                     sector_map_path: Path,
                     mcap_rank: int | None) -> dict[str, float]:
    """Compute all ~30 features for one (symbol, asof) into a flat dict."""
    sector = classify_sector(symbol, sector_map_path)
    feats: dict[str, float] = {}
    feats.update(compute_momentum_features(fetcher, symbol))
    feats.update(compute_perp_features(fetcher, symbol))
    feats.update(compute_volume_features(fetcher, symbol))
    feats.update(compute_technical_features(fetcher, symbol))
    feats.update(compute_sentiment_features(fetcher, symbol,
                                             cache_db=sentiment_cache))
    feats.update(compute_global_features(fetcher, symbol,
                                          cache_db=global_cache,
                                          sector=sector))
    feats["mcap_rank_weight"] = mcap_rank_weight(mcap_rank)
    return feats
