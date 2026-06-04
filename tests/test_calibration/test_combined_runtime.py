import numpy as np
import pytest

from crypto_predictor.calibration.v03_pipeline import (
    fit_smoothed_isotonic,
    apply_calibrated_lookup,
)


def test_refit_after_smoothing_restores_monotonicity():
    """When smoothing pulls a low-n knot below its high-n neighbor's level,
    re-fit must restore non-decreasing order."""
    # Fake isotonic output:  3 knots, middle has very few samples
    x = [0.10, 0.30, 0.50]
    y = [0.60, 0.85, 0.95]
    n = [1000, 5, 1000]  # middle knot will smooth toward 0.5 -> non-monotone
    fit = fit_smoothed_isotonic(
        x=x, y=y, n_per_knot=n,
        prior_alpha=1.0, prior_beta=1.0,
    )
    # After re-fit, y must be non-decreasing
    ys = fit["y"]
    for i in range(len(ys) - 1):
        assert ys[i] <= ys[i + 1] + 1e-9


def test_in_domain_x_uses_isotonic():
    fit = fit_smoothed_isotonic(
        x=[0.0, 0.5], y=[0.4, 0.9], n_per_knot=[100, 100],
    )
    p = apply_calibrated_lookup(fit, direction_raw=0.25)
    assert 0.4 <= p <= 0.9


def test_out_of_domain_x_uses_linear_extrapolation():
    fit = fit_smoothed_isotonic(
        x=[0.0, 0.5], y=[0.4, 0.9], n_per_knot=[100, 100],
    )
    p = apply_calibrated_lookup(fit, direction_raw=0.6)
    assert p > 0.9  # extrapolated above highest knot
    assert p <= 1.0


def test_capped_at_one():
    fit = fit_smoothed_isotonic(
        x=[0.0, 0.5], y=[0.4, 0.9], n_per_knot=[100, 100],
    )
    p = apply_calibrated_lookup(fit, direction_raw=10.0)
    assert p == 1.0


def test_tied_ceiling_knots_redistribute_after_smoothing():
    """The current CHOP 0.9198 problem: two knots tied at the ceiling.
    Smoothing low-n knots toward 0.5 followed by re-fit should produce
    a graduated upper tail rather than a plateau."""
    x = [0.30, 0.45]
    y = [0.9198, 0.9198]  # tied ceiling
    n = [5, 5]  # both low samples
    fit = fit_smoothed_isotonic(
        x=x, y=y, n_per_knot=n,
        prior_alpha=1.0, prior_beta=1.0,
    )
    # After smoothing+refit, the upper knot should be at or above the lower
    assert fit["y"][1] >= fit["y"][0]
    # And both should be pulled below 0.9198
    assert fit["y"][1] < 0.9198


def test_fit_persists_metadata():
    fit = fit_smoothed_isotonic(
        x=[0.0, 0.5], y=[0.4, 0.9], n_per_knot=[100, 100],
        prior_alpha=2.0, prior_beta=3.0,
    )
    assert fit["prior_alpha"] == 2.0
    assert fit["prior_beta"] == 3.0
    assert "x" in fit and "y" in fit
