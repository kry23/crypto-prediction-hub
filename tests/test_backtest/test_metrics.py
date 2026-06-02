import numpy as np

from crypto_predictor.backtest.metrics import (
    hit_rate, mae, brier_score, top_k_alpha,
)


def test_hit_rate_all_correct():
    preds = [1, 1, 1, 0, 0]
    actuals = [1, 1, 1, 0, 0]
    assert hit_rate(preds, actuals) == 1.0


def test_hit_rate_half():
    preds = [1, 1, 0, 0]
    actuals = [1, 0, 0, 1]
    assert hit_rate(preds, actuals) == 0.5


def test_mae_zero_when_perfect():
    assert mae([0.05, -0.03, 0.02], [0.05, -0.03, 0.02]) == 0.0


def test_mae_average_absolute_error():
    assert abs(mae([0.05, 0.0], [0.03, -0.02]) - 0.02) < 1e-9


def test_brier_zero_when_perfect_confidence():
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0


def test_brier_quarter_when_coin_flip():
    bs = brier_score([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1])
    assert abs(bs - 0.25) < 1e-9


def test_top_k_alpha_zero_when_topk_matches_universe():
    universe_returns = [0.01, 0.02, 0.03, 0.04, 0.05]
    top_k_returns = universe_returns
    alpha = top_k_alpha(top_k_returns, universe_returns)
    assert alpha == 0.0


def test_top_k_alpha_positive_when_topk_beats():
    universe_returns = [0.0, 0.0, 0.0, 0.0, 0.0]
    top_k_returns = [0.05, 0.04, 0.03]
    alpha = top_k_alpha(top_k_returns, universe_returns)
    assert alpha > 0.0
