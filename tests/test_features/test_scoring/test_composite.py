from crypto_predictor.scoring.composite import compute_composite


def test_composite_long_high_when_p_up_and_positive_return():
    score = compute_composite(p_up=0.8, expected_return=0.05, anomalous=False)
    assert abs(score - 0.04) < 1e-9


def test_composite_short_uses_p_down_and_abs_return():
    score = compute_composite(p_up=0.3, expected_return=-0.05, anomalous=False)
    assert abs(score - 0.035) < 1e-9


def test_composite_demoted_when_anomalous():
    normal = compute_composite(p_up=0.8, expected_return=0.05, anomalous=False)
    wild = compute_composite(p_up=0.8, expected_return=0.05, anomalous=True)
    assert wild < normal
    assert abs(wild - normal * 0.7) < 1e-9


def test_composite_zero_when_no_signal():
    assert compute_composite(p_up=0.5, expected_return=0.0, anomalous=False) == 0.0
