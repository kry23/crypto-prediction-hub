"""Anomaly flag: marks coins whose feature values are historically extreme."""
from __future__ import annotations

CRITICAL_FEATURES = (
    "funding_z",
    "oi_growth_z",
    "vol_z_24h",
    "sent_velocity",
    "ret_24h_z",
    "ret_7d_z",
)
THRESHOLD = 3.0


def is_anomalous(feats: dict) -> bool:
    """Return True if any critical z-score feature exceeds ±THRESHOLD."""
    for name in CRITICAL_FEATURES:
        v = feats.get(name)
        if v is None:
            continue
        if abs(float(v)) > THRESHOLD:
            return True
    return False
