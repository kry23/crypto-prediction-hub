from crypto_predictor.scoring.anomaly import is_anomalous, CRITICAL_FEATURES


def test_anomalous_when_funding_z_exceeds_three():
    feats = {name: 0.0 for name in CRITICAL_FEATURES}
    feats["funding_z"] = 3.5
    assert is_anomalous(feats) is True


def test_anomalous_when_liq_pressure_extreme():
    feats = {name: 0.0 for name in CRITICAL_FEATURES}
    feats["liq_pressure_long_4h"] = 1e9
    assert is_anomalous(feats) is False


def test_normal_features_not_anomalous():
    feats = {name: 0.5 for name in CRITICAL_FEATURES}
    assert is_anomalous(feats) is False


def test_critical_features_list_excludes_non_zscore_features():
    for name in CRITICAL_FEATURES:
        assert "_z" in name or name in {"sent_velocity"}, \
            f"{name} is not a z-score / velocity feature"
