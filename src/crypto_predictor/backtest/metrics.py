"""Backtest metrics: hit rate, MAE, Brier score, top-K alpha."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def hit_rate(predictions: Sequence[int], actuals: Sequence[int]) -> float:
    """Fraction of correctly predicted directions."""
    if not predictions:
        return 0.0
    arr_p = np.asarray(predictions)
    arr_a = np.asarray(actuals)
    return float((arr_p == arr_a).mean())


def mae(predicted: Sequence[float], actual: Sequence[float]) -> float:
    """Mean absolute error."""
    if not predicted:
        return 0.0
    return float(np.mean(np.abs(np.asarray(predicted) - np.asarray(actual))))


def brier_score(probs: Sequence[float], labels: Sequence[int]) -> float:
    """Brier score = mean of (p - label)^2."""
    if not probs:
        return 0.0
    return float(np.mean((np.asarray(probs) - np.asarray(labels)) ** 2))


def top_k_alpha(top_k_returns: Sequence[float],
                universe_returns: Sequence[float]) -> float:
    """Top-K mean return minus universe mean return."""
    if not top_k_returns or not universe_returns:
        return 0.0
    return float(np.mean(top_k_returns) - np.mean(universe_returns))


def calibration_bucket_table(probs: Sequence[float], labels: Sequence[int],
                              n_buckets: int = 10) -> list[dict]:
    """Bucket probabilities into deciles, report bucket-empirical accuracy."""
    if not probs:
        return []
    arr_p = np.asarray(probs)
    arr_l = np.asarray(labels)
    bins = np.linspace(0.0, 1.0, n_buckets + 1)
    out = []
    for i in range(n_buckets):
        mask = (arr_p >= bins[i]) & (arr_p < bins[i + 1] if i < n_buckets - 1 else arr_p <= bins[i + 1])
        n = int(mask.sum())
        if n == 0:
            continue
        emp = float(arr_l[mask].mean())
        out.append({
            "bucket_low": float(bins[i]),
            "bucket_high": float(bins[i + 1]),
            "predicted_mean": float(arr_p[mask].mean()),
            "empirical_rate": emp,
            "n": n,
        })
    return out
