"""Detect whether a scan's feature families are fully populated or NEUTRAL."""
from __future__ import annotations

from pathlib import Path
from typing import Literal


def _all_zero(features: dict[str, float]) -> bool:
    """True if every value in the dict is 0.0. Empty dict is considered neutral."""
    if not features:
        return True
    return all(v == 0.0 for v in features.values())


def detect_feature_completeness(
    *, sentiment_cache: Path, global_cache: Path,
    sentiment_features: dict[str, float] | None,
    global_features: dict[str, float] | None,
) -> tuple[Literal["full", "degraded"], str | None]:
    """Returns ('full', None) when every family is populated, else
    ('degraded', comma-separated names of NEUTRAL/missing families).

    Semantics per family:
    - cache file absent → family missing → 'degraded'
    - features dict is None → caller skipped per-symbol inspection; rely on
      file-existence only (do NOT mark missing just because dict is None)
    - features dict present but every value is 0.0 → genuinely all-neutral →
      'degraded'
    """
    missing: list[str] = []
    if not sentiment_cache.exists():
        missing.append("sentiment")
    elif sentiment_features is not None and _all_zero(sentiment_features):
        missing.append("sentiment")
    if not global_cache.exists():
        missing.append("global")
    elif global_features is not None and _all_zero(global_features):
        missing.append("global")
    if not missing:
        return ("full", None)
    return ("degraded", ",".join(missing))
