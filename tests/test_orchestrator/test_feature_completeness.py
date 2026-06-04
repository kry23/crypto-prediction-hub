from pathlib import Path

from crypto_predictor.orchestrator.feature_completeness import (
    detect_feature_completeness,
)


def test_both_files_present_with_signal_returns_full(tmp_path: Path):
    sentiment = tmp_path / "sentiment_cache.db"
    sentiment.write_bytes(b"")
    glob = tmp_path / "global_cache.db"
    glob.write_bytes(b"")
    completeness, missing = detect_feature_completeness(
        sentiment_cache=sentiment, global_cache=glob,
        sentiment_features={"news_sent_24h": 0.5},
        global_features={"btc_dom_trend_7d": 0.02},
    )
    assert completeness == "full"
    assert missing is None


def test_sentiment_neutral_returns_degraded_sentiment(tmp_path: Path):
    sentiment = tmp_path / "sentiment_cache.db"
    sentiment.write_bytes(b"")
    glob = tmp_path / "global_cache.db"
    glob.write_bytes(b"")
    completeness, missing = detect_feature_completeness(
        sentiment_cache=sentiment, global_cache=glob,
        sentiment_features={"news_sent_24h": 0.0, "social_sent_24h": 0.0,
                             "sent_velocity": 0.0, "news_volume_z": 0.0},
        global_features={"btc_dom_trend_7d": 0.02},
    )
    assert completeness == "degraded"
    assert missing == "sentiment"


def test_both_neutral_returns_degraded_with_both(tmp_path: Path):
    sentiment = tmp_path / "sentiment_cache.db"
    glob = tmp_path / "global_cache.db"
    completeness, missing = detect_feature_completeness(
        sentiment_cache=sentiment, global_cache=glob,
        sentiment_features=None, global_features=None,
    )
    assert completeness == "degraded"
    assert missing == "sentiment,global"


def test_global_file_absent_returns_degraded_global(tmp_path: Path):
    sentiment = tmp_path / "sentiment_cache.db"
    sentiment.write_bytes(b"")
    glob = tmp_path / "absent.db"
    completeness, missing = detect_feature_completeness(
        sentiment_cache=sentiment, global_cache=glob,
        sentiment_features={"news_sent_24h": 0.5},
        global_features=None,
    )
    assert completeness == "degraded"
    assert missing == "global"


def test_files_present_with_none_dicts_returns_full(tmp_path: Path):
    """When caches EXIST and the caller passed None for the per-symbol features
    (file-existence-only mode), the result is 'full', NOT 'degraded'. Before
    this fix every shadow scan was incorrectly marked degraded because the
    None dict alone triggered 'sentiment,global' missing."""
    sentiment = tmp_path / "sentiment_cache.db"
    sentiment.write_bytes(b"")
    glob = tmp_path / "global_cache.db"
    glob.write_bytes(b"")
    completeness, missing = detect_feature_completeness(
        sentiment_cache=sentiment, global_cache=glob,
        sentiment_features=None, global_features=None,
    )
    assert completeness == "full"
    assert missing is None
