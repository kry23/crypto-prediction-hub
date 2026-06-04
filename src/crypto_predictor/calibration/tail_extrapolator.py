"""Linear extrapolation past the highest isotonic knot."""
from __future__ import annotations


def extrapolate_upper_tail(
    x: list[float], y: list[float], *, target_x: float, cap: float = 1.0,
) -> float:
    """Linear extrapolation past the highest knot, capped at `cap`.

    - target_x <= x[-1]: returns y[-1] (caller handles in-domain via isotonic)
    - target_x > x[-1] and len(x) >= 2: slope = (y[-1] - y[-2]) / (x[-1] - x[-2])
                                          predicted = y[-1] + slope * (target_x - x[-1])
    - len(x) == 1: returns y[0] regardless of target_x
    """
    if not x:
        raise ValueError("x cannot be empty")
    if len(x) != len(y):
        raise ValueError("x and y must be same length")
    if target_x <= x[-1]:
        return min(y[-1], cap)
    if len(x) == 1:
        return min(y[0], cap)
    slope = (y[-1] - y[-2]) / (x[-1] - x[-2])
    predicted = y[-1] + slope * (target_x - x[-1])
    return min(predicted, cap)
