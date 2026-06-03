from unittest.mock import MagicMock

from crypto_predictor.sentiment.newsapi_fetcher import (
    fetch_articles_for_coin, sentiment_from_articles,
)


def test_fetch_articles_for_coin_returns_list(monkeypatch):
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = {
        "status": "ok",
        "articles": [
            {"title": "Bitcoin rallies", "description": "Pump", "publishedAt": "2026-06-02T10:00:00Z"},
            {"title": "BTC stays strong", "description": "Hold", "publishedAt": "2026-06-02T11:00:00Z"},
        ],
    }
    fake_http = MagicMock()
    fake_http.get.return_value = fake_resp
    articles = fetch_articles_for_coin(
        http_client=fake_http, api_key="FAKE", coin="bitcoin", hours_back=24,
    )
    assert len(articles) == 2


def test_sentiment_from_articles_handles_empty():
    score = sentiment_from_articles([])
    assert score == 0.0


def test_sentiment_from_articles_positive_when_bullish_words():
    articles = [
        {"title": "Bitcoin rallies sharply", "description": "surges to new high"},
        {"title": "BTC strong bullish momentum", "description": "rally continues"},
    ]
    score = sentiment_from_articles(articles)
    assert score > 0
