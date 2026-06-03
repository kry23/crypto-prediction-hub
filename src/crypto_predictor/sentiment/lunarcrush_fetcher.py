"""LunarCrush Tier-2 social sentiment fetcher. Returns 0 when no API key set."""
from __future__ import annotations


def fetch_social_sentiment(*, http_client, api_key: str, coin: str) -> float:
    if not api_key:
        return 0.0
    # Plan v0.2 ships scaffold only. Implementation per LunarCrush API docs.
    # Returning 0.0 as graceful default.
    return 0.0
