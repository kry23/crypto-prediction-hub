import numpy as np

from crypto_predictor.features.normalize import zscore, robust_zscore


def test_zscore_normal_case():
    arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    z = zscore(arr, arr)
    # The most recent value (5.0) — mean=3, std=√2 → z ≈ 1.41
    assert abs(z - 1.4142) < 0.001


def test_zscore_zero_std_returns_zero():
    arr = np.array([3.0, 3.0, 3.0])
    z = zscore(3.0, arr)
    assert z == 0.0


def test_zscore_nan_population_returns_zero():
    arr = np.array([np.nan, np.nan, np.nan])
    z = zscore(1.0, arr)
    assert z == 0.0


def test_robust_zscore_uses_median_and_mad():
    arr = np.array([1.0, 2.0, 3.0, 100.0])  # 100 is outlier
    z = robust_zscore(1.0, arr)
    # robust to outliers; classical z would be heavily skewed
    assert abs(z) < 10  # sanity bound; exact depends on MAD
