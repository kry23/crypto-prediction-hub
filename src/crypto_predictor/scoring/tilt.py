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
