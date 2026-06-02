from crypto_predictor.calibration.drift import detect_drift, DriftStatus


def test_no_drift_when_brier_close_to_baseline():
    status = detect_drift(current_brier=0.226, backtest_brier=0.224, delta=0.05)
    assert status == DriftStatus.OK


def test_drift_when_brier_exceeds_baseline_plus_delta():
    status = detect_drift(current_brier=0.30, backtest_brier=0.22, delta=0.05)
    assert status == DriftStatus.DRIFT


def test_no_drift_when_brier_better_than_baseline():
    status = detect_drift(current_brier=0.18, backtest_brier=0.22, delta=0.05)
    assert status == DriftStatus.OK
