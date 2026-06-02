"""Top-K ranking — separate long, short, wild-card slates."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RankedSlate:
    top_long: list[dict] = field(default_factory=list)
    top_short: list[dict] = field(default_factory=list)
    wild_cards: list[dict] = field(default_factory=list)


def rank_predictions(predictions: list[dict],
                     k_long: int = 20, k_short: int = 20) -> RankedSlate:
    """Split predictions into long top-K, short top-K, and wild cards.

    Wild cards are excluded from top-K and go into their own bucket.
    """
    wild = [p for p in predictions if p["confidence_flag"] == "WILD_CARD"]
    normal = [p for p in predictions if p["confidence_flag"] != "WILD_CARD"]

    longs = sorted(
        [p for p in normal if p["prediction"] == "up"],
        key=lambda p: p["composite_score"], reverse=True,
    )[:k_long]
    shorts = sorted(
        [p for p in normal if p["prediction"] == "down"],
        key=lambda p: p["composite_score"], reverse=True,
    )[:k_short]
    wild_sorted = sorted(wild, key=lambda p: p["composite_score"], reverse=True)

    return RankedSlate(top_long=longs, top_short=shorts, wild_cards=wild_sorted)
