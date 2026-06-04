import pytest

from crypto_predictor.calibration.tail_extrapolator import (
    extrapolate_upper_tail,
)


def test_in_domain_x_returns_isotonic_max():
    # When target_x <= max(x), function should return y at the upper knot
    result = extrapolate_upper_tail(
        x=[0.0, 0.3, 0.5], y=[0.4, 0.7, 0.9],
        target_x=0.4, cap=1.0,
    )
    assert result == pytest.approx(0.9, abs=1e-9)


def test_above_highest_knot_linear_extrapolation():
    # Slope = (0.9 - 0.7) / (0.5 - 0.3) = 1.0
    # At target_x=0.6: 0.9 + 1.0 * (0.6 - 0.5) = 1.0 (hits cap)
    result = extrapolate_upper_tail(
        x=[0.0, 0.3, 0.5], y=[0.4, 0.7, 0.9],
        target_x=0.6, cap=1.0,
    )
    assert result == pytest.approx(1.0, abs=1e-9)


def test_extrapolation_capped_at_one():
    result = extrapolate_upper_tail(
        x=[0.0, 0.3, 0.5], y=[0.4, 0.7, 0.9],
        target_x=10.0, cap=1.0,
    )
    assert result == 1.0


def test_slope_from_last_two_knots():
    # Slope = (0.92 - 0.80) / (0.45 - 0.30) = 0.8
    # At target_x=0.50: 0.92 + 0.8 * (0.50 - 0.45) = 0.96
    result = extrapolate_upper_tail(
        x=[0.0, 0.30, 0.45], y=[0.5, 0.80, 0.92],
        target_x=0.50, cap=1.0,
    )
    assert result == pytest.approx(0.96, abs=1e-9)


def test_single_knot_returns_that_value():
    result = extrapolate_upper_tail(
        x=[0.3], y=[0.7],
        target_x=0.5, cap=1.0,
    )
    assert result == 0.7
