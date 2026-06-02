"""Feature normalization — z-score and robust z-score."""
from __future__ import annotations

import numpy as np


def zscore(value, population: np.ndarray) -> float:
    """Standard z-score of `value` against `population`.

    If `value` is a numpy array, the last element is used.
    Returns 0.0 if population is empty, all-NaN, or zero-variance.
    """
    p = np.asarray(population, dtype=float)
    p = p[~np.isnan(p)]
    if p.size == 0:
        return 0.0
    mean = p.mean()
    std = p.std(ddof=0)
    if std == 0 or np.isnan(std):
        return 0.0
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return 0.0
        v = float(value.flat[-1])
    else:
        v = float(value)
    return float((v - mean) / std)


def robust_zscore(value, population: np.ndarray) -> float:
    """Robust z-score using median + median-absolute-deviation."""
    p = np.asarray(population, dtype=float)
    p = p[~np.isnan(p)]
    if p.size == 0:
        return 0.0
    median = np.median(p)
    mad = np.median(np.abs(p - median))
    if mad == 0:
        return 0.0
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return 0.0
        v = float(value.flat[-1])
    else:
        v = float(value)
    return float((v - median) / (1.4826 * mad))
