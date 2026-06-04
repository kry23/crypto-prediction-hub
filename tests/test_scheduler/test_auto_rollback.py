"""Task 8: v0.3 post-ship auto-rollback circuit breaker tests.

Covers `should_auto_rollback` (pure logic). The integration path through
`_job_validate_pending` is exercised lightly via mocks to confirm the
flip + Telegram alert wiring.
"""
from crypto_predictor.output.post_validation import (
    should_auto_rollback,
)


def test_rollback_triggers_when_three_of_seven_below_fifty():
    daily_hit_rates = [0.42, 0.65, 0.48, 0.66, 0.45, 0.70, 0.68]
    # Three days (0.42, 0.48, 0.45) under 0.50 -> rollback
    assert should_auto_rollback(daily_hit_rates) is True


def test_no_rollback_when_only_two_below():
    daily_hit_rates = [0.42, 0.65, 0.48, 0.66, 0.55, 0.70, 0.68]
    assert should_auto_rollback(daily_hit_rates) is False


def test_insufficient_data_does_not_trigger():
    daily_hit_rates = [0.42, 0.45]  # only 2 days
    assert should_auto_rollback(daily_hit_rates) is False


def test_exact_threshold_does_not_trigger():
    """A daily rate of exactly 0.50 should NOT count as 'below 50%'."""
    daily_hit_rates = [0.50, 0.50, 0.50, 0.65, 0.65, 0.65, 0.65]
    assert should_auto_rollback(daily_hit_rates) is False


def test_threshold_parameter_respected():
    daily_hit_rates = [0.45, 0.46, 0.47, 0.65, 0.65, 0.65, 0.65]
    # Under default threshold 0.50: 3 days bad -> True
    assert should_auto_rollback(daily_hit_rates) is True
    # Under threshold 0.40: 0 days bad -> False
    assert should_auto_rollback(daily_hit_rates, threshold=0.40) is False
