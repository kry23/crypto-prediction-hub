import math

import pytest

from crypto_predictor.calibration.beta_binomial import smooth_isotonic_knots


def test_zero_sample_knot_collapses_to_prior():
    smoothed = smooth_isotonic_knots(
        x=[0.0], y=[0.9], n_per_knot=[0],
        prior_alpha=1.0, prior_beta=1.0,
    )
    assert smoothed == pytest.approx([0.5], abs=1e-9)


def test_large_sample_knot_preserves_empirical():
    smoothed = smooth_isotonic_knots(
        x=[0.0], y=[0.9], n_per_knot=[10000],
        prior_alpha=1.0, prior_beta=1.0,
    )
    assert smoothed[0] == pytest.approx(0.9, abs=1e-3)


def test_intermediate_sample_knot_partially_smoothed():
    smoothed = smooth_isotonic_knots(
        x=[0.0], y=[0.9], n_per_knot=[10],
        prior_alpha=1.0, prior_beta=1.0,
    )
    expected = (10 * 0.9 + 1.0) / (10 + 1.0 + 1.0)
    assert smoothed[0] == pytest.approx(expected, abs=1e-9)


def test_all_correct_knot_pulled_below_one():
    # Knot with y=1.0 (all correct in training) and small n must regress below 1.0
    smoothed = smooth_isotonic_knots(
        x=[0.5], y=[1.0], n_per_knot=[5],
        prior_alpha=1.0, prior_beta=1.0,
    )
    assert smoothed[0] < 1.0
    assert smoothed[0] == pytest.approx((5 + 1) / (5 + 2), abs=1e-9)


def test_all_wrong_knot_pulled_above_zero():
    smoothed = smooth_isotonic_knots(
        x=[0.5], y=[0.0], n_per_knot=[5],
        prior_alpha=1.0, prior_beta=1.0,
    )
    assert smoothed[0] > 0.0
    assert smoothed[0] == pytest.approx(1.0 / 7.0, abs=1e-9)


def test_aggressive_prior_pulls_harder():
    default = smooth_isotonic_knots(
        x=[0.0], y=[0.92], n_per_knot=[10],
        prior_alpha=1.0, prior_beta=1.0,
    )[0]
    aggressive = smooth_isotonic_knots(
        x=[0.0], y=[0.92], n_per_knot=[10],
        prior_alpha=5.0, prior_beta=5.0,
    )[0]
    assert abs(aggressive - 0.5) < abs(default - 0.5)
