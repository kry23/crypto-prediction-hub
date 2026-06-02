# Plan B backtest
**Window**: 2026-03-27T00:00:00+00:00..2026-05-26T00:00:00+00:00
> survivorship_bias: present - backtest excludes coins delisted during the window.

## Overall

- **Hit rate**: 54.3%
- **MAE**: 2.72%
- **Brier score**: 0.247
- **Predictions**: 1,647

## Per regime

| Regime | Hit rate | n |
|---|---|---|
| BULL | 56.2% | 810 |
| CHOP | 52.4% | 837 |

## Calibration buckets

| P bucket | predicted | empirical | n |
|---|---|---|---|
| 0.0-0.1 | 0.000 | 0.000 | 2 |
| 0.3-0.4 | 0.375 | 0.375 | 200 |
| 0.4-0.5 | 0.466 | 0.466 | 616 |
| 0.5-0.6 | 0.528 | 0.528 | 829 |

## Top-K alpha (vs equal-weight universe)

- **Long alpha**: -0.46%
- **Short alpha**: +0.00%
- **Combined**: -0.46%
