from crypto_predictor.scoring.direction import compute_direction_raw, DEFAULT_WEIGHTS


def test_direction_raw_in_unit_range():
    feats = {
        "ret_15m_z": 2.0, "ret_1h_z": 2.0, "ret_4h_z": 2.0, "ret_24h_z": 2.0,
        "ret_7d_z": 2.0, "mom_consistency": 0.9,
        "funding_z": -3.0, "funding_extreme": 1.0,
        "oi_growth_z": 1.0, "liq_pressure_short_4h": 1e6,
        "liq_pressure_long_4h": 0.0,
        "vol_z_24h": 2.0,
        "rsi_14_1h": 50.0, "macd_hist_1h": 0.5, "bb_position_1h": 0.5,
        "price_vs_sma50": 0.05,
        "news_sent_24h": 0.0, "social_sent_24h": 0.0,
        "sent_velocity": 0.0, "news_volume_z": 0.0,
        "btc_dom_trend_7d": 0.0, "eth_btc_trend_7d": 0.0,
        "total_mcap_z": 0.0, "sector_strength_24h": 0.0,
        "coin_btc_corr_30d": 0.5, "mcap_rank_weight": 1.0,
    }
    raw = compute_direction_raw(feats)
    assert -1.0 <= raw <= 1.0
    assert raw > 0.3


def test_direction_raw_neutral_when_all_zero():
    feats = {"mcap_rank_weight": 1.0, "coin_btc_corr_30d": 0.5}
    raw = compute_direction_raw(feats)
    assert abs(raw) < 0.01


def test_direction_raw_custom_weights_change_output():
    feats = {
        "ret_15m_z": 2.0, "ret_1h_z": 2.0, "ret_4h_z": 2.0, "ret_24h_z": 2.0,
        "ret_7d_z": 2.0, "mom_consistency": 0.9,
        "mcap_rank_weight": 1.0, "coin_btc_corr_30d": 0.5,
    }
    raw_default = compute_direction_raw(feats)
    custom = dict(DEFAULT_WEIGHTS)
    custom["momentum"] = 0.80
    custom["perp"] = 0.05
    custom["volume"] = 0.05
    custom["technical"] = 0.05
    custom["sentiment"] = 0.025
    custom["global"] = 0.025
    raw_momentum_heavy = compute_direction_raw(feats, weights=custom)
    assert raw_momentum_heavy > raw_default


def test_default_weights_sum_to_one():
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9


def test_compute_direction_raw_for_regime_uses_regime_weights():
    from crypto_predictor.scoring.direction import (
        compute_direction_raw_for_regime, DEFAULT_REGIME_WEIGHTS,
    )
    feats = {"ret_24h_z": 2.0, "mom_consistency": 0.9, "mcap_rank_weight": 1.0}
    # CHOP should use lower momentum weight than BULL
    raw_bull = compute_direction_raw_for_regime(feats, "BULL")
    raw_chop = compute_direction_raw_for_regime(feats, "CHOP")
    # CHOP momentum weight (0.10) < BULL momentum weight (0.20)
    # -> raw_chop should be less positive than raw_bull for momentum-dominant features
    assert raw_chop < raw_bull
