# tests/test_orchestrator/test_cache_warnings.py
"""Once-per-scan operator warnings when sentiment/global caches are missing."""
from pathlib import Path

from crypto_predictor.orchestrator.run import _log_missing_caches


def _captured(capsys) -> str:
    cap = capsys.readouterr()
    return cap.out + cap.err


def test_warns_when_both_caches_missing(tmp_path: Path, capsys):
    sentiment = tmp_path / "sentiment.db"
    global_ = tmp_path / "global.db"
    _log_missing_caches(sentiment, global_)
    captured = _captured(capsys)
    assert captured.count("cache_missing") == 2
    assert '"sentiment"' in captured or "cache=sentiment" in captured
    assert '"global"' in captured or "cache=global" in captured


def test_no_warn_when_both_caches_present(tmp_path: Path, capsys):
    sentiment = tmp_path / "sentiment.db"
    global_ = tmp_path / "global.db"
    sentiment.write_bytes(b"")
    global_.write_bytes(b"")
    _log_missing_caches(sentiment, global_)
    assert "cache_missing" not in _captured(capsys)


def test_only_sentiment_missing(tmp_path: Path, capsys):
    sentiment = tmp_path / "sentiment.db"
    global_ = tmp_path / "global.db"
    global_.write_bytes(b"")
    _log_missing_caches(sentiment, global_)
    captured = _captured(capsys)
    assert captured.count("cache_missing") == 1
    assert '"sentiment"' in captured or "cache=sentiment" in captured
    assert '"global"' not in captured and "cache=global" not in captured
