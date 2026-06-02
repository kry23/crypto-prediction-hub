"""Sentiment dampener by mcap rank (top 100 = full trust, smaller = attenuated)."""
from __future__ import annotations


def mcap_rank_weight(rank: int | None) -> float:
    if rank is None:
        return 0.4
    if rank <= 100:
        return 1.0
    if rank <= 200:
        return 0.7
    return 0.4
