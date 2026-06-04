"""Fit-time: isotonic -> smooth -> re-fit isotonic. Predict-time: lookup + extrapolate."""
from __future__ import annotations

import numpy as np
from sklearn.isotonic import IsotonicRegression

from crypto_predictor.calibration.beta_binomial import smooth_isotonic_knots
from crypto_predictor.calibration.tail_extrapolator import (
    extrapolate_upper_tail,
)


def fit_smoothed_isotonic(
    *, x: list[float], y: list[float], n_per_knot: list[int],
    prior_alpha: float = 1.0, prior_beta: float = 1.0,
) -> dict:
    """Apply beta-binomial smoothing then re-fit isotonic to restore monotonicity.

    Returns dict with keys: x, y (smoothed-and-refit knot values),
    prior_alpha, prior_beta, n_per_knot (preserved for audit).
    """
    smoothed_y = smooth_isotonic_knots(
        x=x, y=y, n_per_knot=n_per_knot,
        prior_alpha=prior_alpha, prior_beta=prior_beta,
    )
    # Re-fit isotonic weighted by n_per_knot to restore non-decreasing y
    ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
    ir.fit(np.array(x), np.array(smoothed_y),
            sample_weight=np.array(n_per_knot, dtype=float))
    return {
        "x": ir.X_thresholds_.tolist(),
        "y": ir.y_thresholds_.tolist(),
        "prior_alpha": prior_alpha,
        "prior_beta": prior_beta,
        "n_per_knot": n_per_knot,
    }


def apply_calibrated_lookup(fit: dict, *, direction_raw: float) -> float:
    """Lookup the calibrated probability for a direction_raw value.

    In-domain (direction_raw <= max(x)): isotonic interpolation between knots.
    Out-of-domain (direction_raw > max(x)): linear extrapolation, capped at 1.0.
    """
    x = fit["x"]
    y = fit["y"]
    if direction_raw <= x[-1]:
        # Linear interpolation between bracketing knots
        if direction_raw <= x[0]:
            return y[0]
        for i in range(len(x) - 1):
            if x[i] <= direction_raw <= x[i + 1]:
                if x[i + 1] == x[i]:
                    return y[i]
                t = (direction_raw - x[i]) / (x[i + 1] - x[i])
                return y[i] + t * (y[i + 1] - y[i])
        return y[-1]  # numerical edge
    return extrapolate_upper_tail(x=x, y=y, target_x=direction_raw, cap=1.0)
