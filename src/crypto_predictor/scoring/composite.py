"""Composite score for ranking."""
from __future__ import annotations


def compute_composite(*, p_up: float, expected_return: float,
                      anomalous: bool) -> float:
    """Composite = max(p_up, p_down) × |expected_return|; demoted by 0.7 if anomalous."""
    p_down = 1.0 - p_up
    base = max(p_up, p_down) * abs(expected_return)
    return base * 0.7 if anomalous else base
