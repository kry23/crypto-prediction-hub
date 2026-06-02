"""Tilt functions per feature family. Each returns value in [-1, +1]."""
from __future__ import annotations


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _get(feats: dict, name: str, default: float = 0.0) -> float:
    v = feats.get(name, default)
    if v is None:
        return default
    return float(v)


def tilt_momentum(feats: dict) -> float:
    """Weighted average of multi-timeframe return z-scores + consistency."""
    ret_components = (
        0.15 * _get(feats, "ret_15m_z") +
        0.20 * _get(feats, "ret_1h_z") +
        0.20 * _get(feats, "ret_4h_z") +
        0.25 * _get(feats, "ret_24h_z") +
        0.10 * _get(feats, "ret_7d_z")
    )
    base = _clip(ret_components / 2.0)
    cons_tilt = (_get(feats, "mom_consistency", 0.5) - 0.5) * 2.0
    return _clip(0.7 * base + 0.3 * cons_tilt)


def tilt_perp(feats: dict) -> float:
    """Perp microstructure tilt: funding mean-reversion + OI confirmation + liquidation pressure."""
    funding_z = _get(feats, "funding_z")
    funding_tilt = -_clip(funding_z / 2.0)

    ret_4h_sign = 1.0 if _get(feats, "ret_4h_z") > 0 else (-1.0 if _get(feats, "ret_4h_z") < 0 else 0.0)
    oi_growth_z = _get(feats, "oi_growth_z")
    oi_confirm = ret_4h_sign * _clip(oi_growth_z)

    s = _get(feats, "liq_pressure_short_4h")
    l = _get(feats, "liq_pressure_long_4h")
    total = s + l + 1.0
    liq_tilt = _clip((s - l) / total)

    return _clip(0.4 * funding_tilt + 0.3 * oi_confirm + 0.3 * liq_tilt)


def tilt_volume(feats: dict) -> float:
    """Volume confirms direction; high vol_z amplifies the recent 24h return signal."""
    vol_z = _get(feats, "vol_z_24h")
    ret_24h = _get(feats, "ret_24h_z")
    amp = _clip(vol_z / 2.0)
    direction = _clip(ret_24h / 2.0)
    return _clip(amp * direction)


def tilt_technical(feats: dict) -> float:
    """Technical: RSI mean-reversion + MACD + BB + SMA50 trend."""
    rsi = _get(feats, "rsi_14_1h", 50.0)
    rsi_tilt = (50.0 - rsi) / 50.0
    macd = _clip(_get(feats, "macd_hist_1h") / 2.0)
    bb_pos = _get(feats, "bb_position_1h", 0.5)
    bb_tilt = (0.5 - bb_pos) * 2.0
    sma = _clip(_get(feats, "price_vs_sma50") * 10.0)
    return _clip(0.4 * rsi_tilt + 0.25 * macd + 0.20 * bb_tilt + 0.15 * sma)


def tilt_sentiment(feats: dict) -> float:
    """Sentiment composite. Returns 0 if no sentiment cache data exists."""
    news = _get(feats, "news_sent_24h")
    social = _get(feats, "social_sent_24h")
    velocity = _get(feats, "sent_velocity")
    vol = _clip(_get(feats, "news_volume_z") / 2.0)
    base = 0.5 * news + 0.3 * social + 0.2 * velocity
    return _clip(base * (1.0 + 0.5 * abs(vol)) * (1.0 if base != 0 else 0.0))


def tilt_global(feats: dict) -> float:
    """Global / cross-coin tilt: BTC dom + ETH/BTC + total mcap + sector strength."""
    btc_dom = _get(feats, "btc_dom_trend_7d")
    eth_btc = _get(feats, "eth_btc_trend_7d")
    total_mcap = _clip(_get(feats, "total_mcap_z") / 2.0)
    sector = _clip(_get(feats, "sector_strength_24h") * 20.0)
    dom_tilt = -_clip(btc_dom * 20.0)
    eth_btc_tilt = _clip(eth_btc * 20.0)
    return _clip(0.3 * dom_tilt + 0.2 * eth_btc_tilt + 0.2 * total_mcap + 0.3 * sector)
