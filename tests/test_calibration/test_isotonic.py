import numpy as np

from crypto_predictor.calibration.isotonic import (
    fit_calibration, predict_probability, RegimeCalibrators,
)


def test_fit_returns_calibrators_per_regime():
    np.random.seed(0)
    rows = []
    for regime in ("BULL", "BEAR", "CHOP"):
        for _ in range(100):
            raw = np.random.uniform(-1, 1)
            label = 1 if raw > 0 and np.random.random() < 0.7 else (
                1 if raw < 0 and np.random.random() < 0.3 else 0
            )
            rows.append((raw, label, regime))
    calibs = fit_calibration(rows)
    assert isinstance(calibs, RegimeCalibrators)
    for regime in ("BULL", "BEAR", "CHOP"):
        assert calibs.has(regime)


def test_predict_probability_in_unit_interval():
    np.random.seed(1)
    rows = []
    for _ in range(200):
        raw = np.random.uniform(-1, 1)
        label = 1 if raw > 0 else 0
        rows.append((raw, label, "BULL"))
    calibs = fit_calibration(rows)
    for raw in [-1.0, -0.5, 0.0, 0.5, 1.0]:
        p = predict_probability(calibs, raw_score=raw, regime="BULL")
        assert 0.0 <= p <= 1.0


def test_predict_probability_monotonic_in_raw():
    np.random.seed(2)
    rows = []
    for _ in range(500):
        raw = np.random.uniform(-1, 1)
        label = 1 if raw + np.random.normal(0, 0.3) > 0 else 0
        rows.append((raw, label, "BULL"))
    calibs = fit_calibration(rows)
    ps = [predict_probability(calibs, raw_score=r, regime="BULL")
          for r in np.linspace(-1, 1, 11)]
    for i in range(len(ps) - 1):
        assert ps[i] <= ps[i+1] + 1e-6


def test_predict_probability_returns_0_5_for_unknown_regime():
    calibs = fit_calibration([(0.0, 0, "BULL")])
    p = predict_probability(calibs, raw_score=0.5, regime="UNKNOWN")
    assert p == 0.5
