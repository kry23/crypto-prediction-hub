from crypto_predictor.scoring.tilt import tilt_perp


def test_tilt_perp_extreme_negative_funding_is_bullish():
    feats = {
        "funding_z": -3.0, "funding_extreme": 1.0,
        "oi_growth_z": 0.5, "ret_4h_z": 0.5,
        "liq_pressure_short_4h": 1_000_000.0,
        "liq_pressure_long_4h": 0.0,
    }
    t = tilt_perp(feats)
    assert t > 0.4


def test_tilt_perp_extreme_positive_funding_is_bearish():
    feats = {
        "funding_z": 3.0, "funding_extreme": 1.0,
        "oi_growth_z": 0.0, "ret_4h_z": 0.0,
        "liq_pressure_short_4h": 0.0,
        "liq_pressure_long_4h": 1_000_000.0,
    }
    t = tilt_perp(feats)
    assert t < -0.4


def test_tilt_perp_oi_growth_confirms_direction():
    feats = {
        "funding_z": 0.0, "funding_extreme": 0.0,
        "oi_growth_z": 1.0, "ret_4h_z": 1.0,
        "liq_pressure_short_4h": 0.0,
        "liq_pressure_long_4h": 0.0,
    }
    t = tilt_perp(feats)
    assert t > 0.1


def test_tilt_perp_clipped():
    feats = {
        "funding_z": -10.0, "funding_extreme": 1.0,
        "oi_growth_z": 10.0, "ret_4h_z": 10.0,
        "liq_pressure_short_4h": 1e12,
        "liq_pressure_long_4h": 0.0,
    }
    t = tilt_perp(feats)
    assert -1.0 <= t <= 1.0


def test_tilt_perp_handles_missing_features():
    assert tilt_perp({}) == 0.0
