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
