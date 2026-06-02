"""Calibration drift detection."""
from __future__ import annotations

from enum import Enum


class DriftStatus(str, Enum):
    OK = "OK"
    DRIFT = "DRIFT"


def detect_drift(*, current_brier: float, backtest_brier: float,
                 delta: float = 0.05) -> DriftStatus:
    if current_brier > backtest_brier + delta:
        return DriftStatus.DRIFT
    return DriftStatus.OK
