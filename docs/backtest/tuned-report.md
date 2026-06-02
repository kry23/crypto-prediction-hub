# Plan B backtest
**Window**: 2026-03-27T00:00:00+00:00..2026-05-26T00:00:00+00:00
> survivorship_bias: present - backtest excludes coins delisted during the window.

## Overall

- **Hit rate**: 56.6%
- **MAE**: 2.65%
- **Brier score**: 0.243
- **Predictions**: 1,647

## Per regime

| Regime | Hit rate | n |
|---|---|---|
| BULL | 56.2% | 810 |
| CHOP | 57.1% | 837 |

## Calibration buckets

| P bucket | predicted | empirical | n |
|---|---|---|---|
| 0.3-0.4 | 0.379 | 0.379 | 385 |
| 0.4-0.5 | 0.457 | 0.457 | 470 |
| 0.5-0.6 | 0.540 | 0.540 | 713 |
| 0.6-0.7 | 0.679 | 0.679 | 78 |
| 0.9-1.0 | 1.000 | 1.000 | 1 |

## Top-K alpha (vs equal-weight universe)

- **Long alpha**: -0.47%
- **Short alpha**: +0.00%
- **Combined**: -0.47%
