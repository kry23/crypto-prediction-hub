"""NewsAPI + sentiment scoring (Tier 1 — top 100 mcap)."""
from __future__ import annotations

import re

NEWSAPI_BASE = "https://newsapi.org/v2/everything"

POSITIVE = {"rally", "surge", "bullish", "moon", "pump", "high", "strong",
            "breakout", "soar", "gain"}
NEGATIVE = {"crash", "dump", "bearish", "fall", "drop", "decline", "weak",
            "low", "tank", "loss", "plunge"}


def fetch_articles_for_coin(*, http_client, api_key: str, coin: str,
                             hours_back: int = 24) -> list[dict]:
    """Pull articles for a coin name (e.g. 'bitcoin'). Returns list of article dicts."""
    if not api_key:
        return []
    from datetime import datetime, timedelta, timezone
    # NewsAPI accepts YYYY-MM-DD; full ISO datetime returns 0 results
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).strftime("%Y-%m-%d")
    params = {
        "q": coin,
        "from": since,
        "sortBy": "publishedAt",
        "language": "en",
        "apiKey": api_key,
        "pageSize": 30,
    }
    resp = http_client.get(NEWSAPI_BASE, params=params)
    if resp.status_code != 200:
        return []
    return resp.json().get("articles", [])


def sentiment_from_articles(articles: list[dict]) -> float:
    """Naive +/- vocab scoring; returns mean in [-1, +1]."""
    if not articles:
        return 0.0
    scores = []
    for art in articles:
        text = ((art.get("title") or "") + " " +
                (art.get("description") or "")).lower()
        words = set(re.findall(r"\b[a-z]+\b", text))
        pos = len(words & POSITIVE)
        neg = len(words & NEGATIVE)
        total = pos + neg
        if total == 0:
            scores.append(0.0)
        else:
            scores.append((pos - neg) / total)
    return float(sum(scores) / len(scores))
