from crypto_predictor.scoring.tilt import tilt_momentum


def test_tilt_momentum_strong_positive():
    feats = {
        "ret_15m_z": 2.0, "ret_1h_z": 2.0, "ret_4h_z": 2.0,
        "ret_24h_z": 2.0, "ret_7d_z": 2.0, "mom_consistency": 0.9,
    }
    t = tilt_momentum(feats)
    assert 0.5 < t <= 1.0


def test_tilt_momentum_strong_negative():
    feats = {
        "ret_15m_z": -2.0, "ret_1h_z": -2.0, "ret_4h_z": -2.0,
        "ret_24h_z": -2.0, "ret_7d_z": -2.0, "mom_consistency": 0.1,
    }
    t = tilt_momentum(feats)
    assert -1.0 <= t < -0.5


def test_tilt_momentum_neutral_when_mixed():
    feats = {
        "ret_15m_z": 0.0, "ret_1h_z": 0.0, "ret_4h_z": 0.0,
        "ret_24h_z": 0.0, "ret_7d_z": 0.0, "mom_consistency": 0.5,
    }
    t = tilt_momentum(feats)
    assert abs(t) < 0.1


def test_tilt_momentum_clipped_to_unit_range():
    feats = {
        "ret_15m_z": 10.0, "ret_1h_z": 10.0, "ret_4h_z": 10.0,
        "ret_24h_z": 10.0, "ret_7d_z": 10.0, "mom_consistency": 1.0,
    }
    t = tilt_momentum(feats)
    assert -1.0 <= t <= 1.0


def test_tilt_momentum_handles_missing_features():
    t = tilt_momentum({})
    assert t == 0.0
