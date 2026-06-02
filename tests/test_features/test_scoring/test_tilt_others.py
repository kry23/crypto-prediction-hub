from crypto_predictor.scoring.tilt import (
    tilt_volume, tilt_technical, tilt_sentiment, tilt_global,
)


def test_tilt_volume_amplifies_with_high_vol_z():
    feats = {"vol_z_24h": 2.0, "ret_24h_z": 1.0}
    t = tilt_volume(feats)
    assert t > 0.0


def test_tilt_volume_neutral_when_low_volume():
    feats = {"vol_z_24h": 0.0, "ret_24h_z": 0.0}
    assert abs(tilt_volume(feats)) < 0.1


def test_tilt_technical_oversold_is_bullish():
    feats = {"rsi_14_1h": 25.0, "rsi_oversold": 1.0, "rsi_overbought": 0.0,
             "macd_hist_1h": 0.5, "bb_position_1h": 0.0, "price_vs_sma50": -0.05}
    t = tilt_technical(feats)
    assert t > 0.0


def test_tilt_technical_overbought_is_bearish():
    feats = {"rsi_14_1h": 78.0, "rsi_oversold": 0.0, "rsi_overbought": 1.0,
             "macd_hist_1h": -0.5, "bb_position_1h": 1.0, "price_vs_sma50": 0.1}
    t = tilt_technical(feats)
    assert t < 0.0


def test_tilt_sentiment_positive_news_is_bullish():
    feats = {"news_sent_24h": 0.6, "social_sent_24h": 0.4,
             "sent_velocity": 0.3, "news_volume_z": 1.5}
    t = tilt_sentiment(feats)
    assert t > 0.2


def test_tilt_sentiment_returns_zero_when_neutral():
    feats = {"news_sent_24h": 0.0, "social_sent_24h": 0.0,
             "sent_velocity": 0.0, "news_volume_z": 0.0}
    assert tilt_sentiment(feats) == 0.0


def test_tilt_global_btc_dom_rising_helps_btc_short():
    feats = {"btc_dom_trend_7d": 0.05, "eth_btc_trend_7d": 0.0,
             "total_mcap_z": 0.0, "sector_strength_24h": 0.0}
    t = tilt_global(feats)
    assert t < 0.1


def test_all_tilts_clipped_to_unit_range():
    big = {k: 100.0 for k in [
        "vol_z_24h", "ret_24h_z", "rsi_14_1h", "rsi_oversold", "rsi_overbought",
        "macd_hist_1h", "bb_position_1h", "price_vs_sma50",
        "news_sent_24h", "social_sent_24h", "sent_velocity", "news_volume_z",
        "btc_dom_trend_7d", "eth_btc_trend_7d", "total_mcap_z", "sector_strength_24h",
    ]}
    for fn in [tilt_volume, tilt_technical, tilt_sentiment, tilt_global]:
        t = fn(big)
        assert -1.0 <= t <= 1.0
