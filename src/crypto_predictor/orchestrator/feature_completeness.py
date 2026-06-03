"""Detect whether a scan's feature families are fully populated or NEUTRAL."""
from __future__ import annotations

from pathlib import Path
from typing import Literal


def _is_all_neutral(features: dict[str, float] | None) -> bool:
    """True if features is None or every value is 0.0."""
    if not features:
        return True
    return all(v == 0.0 for v in features.values())


def detect_feature_completeness(
    *, sentiment_cache: Path, global_cache: Path,
    sentiment_features: dict[str, float] | None,
    global_features: dict[str, float] | None,
) -> tuple[Literal["full", "degraded"], str | None]:
    """Returns ('full', None) when every family is populated, else
    ('degraded', comma-separated names of NEUTRAL/missing families)."""
    missing: list[str] = []
    if not sentiment_cache.exists() or _is_all_neutral(sentiment_features):
        missing.append("sentiment")
    if not global_cache.exists() or _is_all_neutral(global_features):
        missing.append("global")
    if not missing:
        return ("full", None)
    return ("degraded", ",".join(missing))
