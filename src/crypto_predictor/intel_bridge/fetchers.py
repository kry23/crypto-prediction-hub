"""Adapter interfaces for whale and news data sources.

For v1.0 we ship stub implementations that return empty lists. Day-14
swaps in real fetchers (crypto_intel_hub MCP modules or HTTP polls of
the standalone server). The adapter interface stays stable so the
swap is one-file.
"""
from __future__ import annotations

from datetime import datetime
from typing import Protocol


class WhaleEvent(dict):
    """Schema:
        chain: str
        symbol: str | None
        tx_hash: str
        amount_usd: float
        from_label: str | None
        to_label: str | None
        ts: datetime (UTC)
        raw_json: dict (the underlying source response)
    """


class NewsEvent(dict):
    """Schema:
        category: str   (one of: hack, regulation, macro, altcoin)
        severity: str   (low|medium|high|critical)
        title: str
        url: str | None
        source: str | None
        symbols_mentioned: list[str]
        sentiment: float (-1..+1)
        ts: datetime (UTC)
        raw_json: dict
    """


class WhaleFetcher(Protocol):
    def fetch_recent(self, *, since: datetime) -> list[WhaleEvent]: ...


class NewsFetcher(Protocol):
    def fetch_recent(self, *, since: datetime) -> list[NewsEvent]: ...


class StubWhaleFetcher:
    """v1.0 default — returns []. Day-14 swaps for the real one."""

    def fetch_recent(self, *, since: datetime) -> list[WhaleEvent]:
        return []


class StubNewsFetcher:
    """v1.0 default — returns []."""

    def fetch_recent(self, *, since: datetime) -> list[NewsEvent]:
        return []
