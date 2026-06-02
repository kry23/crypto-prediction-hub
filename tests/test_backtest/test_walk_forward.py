from datetime import datetime, timezone

from crypto_predictor.backtest.walk_forward import iter_windows, WalkForwardWindow


def test_iter_windows_produces_correct_slices():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 1, tzinfo=timezone.utc)
    windows = list(iter_windows(start=start, end=end,
                                train_months=3, cal_months=1, val_months=1,
                                slide_days=7))
    assert len(windows) > 0
    w0 = windows[0]
    assert isinstance(w0, WalkForwardWindow)
    assert w0.train_start == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert w0.val_end <= end


def test_iter_windows_slides_forward():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 1, tzinfo=timezone.utc)
    windows = list(iter_windows(start=start, end=end,
                                train_months=3, cal_months=1, val_months=1,
                                slide_days=7))
    if len(windows) >= 2:
        delta = (windows[1].train_start - windows[0].train_start).days
        assert delta == 7
