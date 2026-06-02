"""Walk-forward window iterator. Each iteration yields train/cal/val slice."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: datetime
    train_end: datetime
    cal_start: datetime
    cal_end: datetime
    val_start: datetime
    val_end: datetime


def _add_months(dt: datetime, n: int) -> datetime:
    return dt + timedelta(days=30 * n)


def iter_windows(*, start: datetime, end: datetime,
                 train_months: int, cal_months: int, val_months: int,
                 slide_days: int = 7) -> Iterator[WalkForwardWindow]:
    """Yield rolling (train, cal, val) slices that fit within [start, end]."""
    cursor = start
    while True:
        train_start = cursor
        train_end = _add_months(train_start, train_months)
        cal_start = train_end
        cal_end = _add_months(cal_start, cal_months)
        val_start = cal_end
        val_end = _add_months(val_start, val_months)
        if val_end > end:
            break
        yield WalkForwardWindow(
            train_start=train_start, train_end=train_end,
            cal_start=cal_start, cal_end=cal_end,
            val_start=val_start, val_end=val_end,
        )
        cursor = cursor + timedelta(days=slide_days)
