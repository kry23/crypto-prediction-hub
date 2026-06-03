# Calibration ceiling analysis — 2026-06-03

**Source**: `data/calibration_1_5_4.json` (the active calibration version, fit window 2026-03-27 → 2026-05-26).
**Run it**: `python scripts/calibration_ceiling_analysis.py`

## TL;DR

The CHOP regime's calibration map saturates at **p = 0.9198, not 1.0**, and any `direction_raw ≥ +0.3035` gets clipped to that ceiling. The current `predictions.db` has **5 coins tied at exactly p = 0.9198** — they are indistinguishable in the probability dimension and ranked only by their magnitude estimates. The BULL regime does not have this problem (ceiling = 1.0).

This is a sharpening artifact of the isotonic fit, not a calibration bug. It does not currently degrade top-K ranking (composite tie-breaks by |expected return|), but it does throw away conviction-tier information at the top of the slate.

## Per-regime map shape

| regime | knots | x range | y range | ceiling | first-x at ceiling | # knots at ceiling |
|---|---|---|---|---|---|---|
| BULL | 24 | [−0.4634, +0.5449] | [0.0000, **1.0000**] | 1.0000 | +0.5449 | 1 |
| CHOP | 46 | [−0.5146, +0.4560] | [0.0000, **0.9198**] | **0.9198** | +0.3035 | 2 |

BEAR is absent from this calibration file — the 60-day fit window did not contain enough BEAR-labeled days to fit a regime-specific map. (When `regime=BEAR` is observed live, the runner falls back to the global pre-Phase-1.5 calibration at `data/calibration_map.json`.)

## Why CHOP saturates at 0.9198

The CHOP y-histogram makes the artifact obvious — the top two bins are empty (`[0.8278, 0.8738)`, `[0.7818, 0.8278)`), then two knots land at 0.9198 and nothing higher. The isotonic regression saw:

- ~46 knot points (the fit window had enough CHOP samples to support fine-grained mapping)
- The top 2 training points both had outcome=1 (correct prediction) after the model's confidence had already moved them above `direction_raw ≈ 0.30`
- Isotonic constrains y to be monotone non-decreasing, so once the top bin is at 0.9198 the curve cannot continue rising without a higher training-data observation, which doesn't exist in the 60-day window

This is a **small-sample artifact**: with more upper-tail data points, the isotonic curve would either continue past 0.9198 toward 1.0 or stay at exactly 0.9198 if 91.98% really is the empirical hit rate at the top.

## CHOP y-histogram (sharpness signature)

```
[0.000, 0.046)   4  ####################
[0.046, 0.092)   0
[0.092, 0.138)   4  ####################
[0.138, 0.184)   0
...
[0.598, 0.644)   6  ##############################
[0.644, 0.690)   0
[0.690, 0.736)   6  ##############################
[0.736, 0.782)   6  ##############################
[0.782, 0.828)   0
[0.828, 0.874)   0
[0.874, 0.920)   2  ##########
```

The two empty bins immediately below the ceiling (`[0.7818, 0.8278)`, `[0.8278, 0.8738)`) confirm the saturation: there is no graduated approach toward 0.92, just a jump from a 0.736–0.782 plateau straight to the ceiling.

## Coins currently at the CHOP ceiling

Five predictions sit at p = 0.9198 within ±0.001:

| symbol | p_direction | expected return | confidence_flag | side |
|---|---|---|---|---|
| BERA/USDT:USDT | 0.9198 | +2.55% | NORMAL | up |
| CELO/USDT:USDT | 0.9198 | +2.15% | NORMAL | up |
| ATOM/USDT:USDT | 0.9198 | +1.82% | NORMAL | up |
| SAND/USDT:USDT | 0.9198 | +1.79% | NORMAL | up |
| DOOD/USDT:USDT | 0.9198 | +2.23% | WILD_CARD | up |

All five are long. All are CHOP. The composite ordering between them reduces to just `|expected return|`. The fact that DOOD is also a wild card means it gets routed away from the main bucket — and the other four (BERA, CELO, ATOM, SAND) compete for the same top slots in the long top-K with identical confidence flags and identical calibrated probabilities, separated only by return magnitudes that differ by 76 basis points (BERA 2.55% vs SAND 1.79%).

## Does this hurt today?

**Not in current top-K ranking.** The ranker uses composite = p × |expected return|, and with p clamped, tie-breaking by |er| is fine — coins with bigger expected moves still rise to the top. The five tied coins do not all show up in the daily Telegram top-3 because the magnitude ordering separates them.

**It does hurt downstream calibration scoring.** The Brier score and MAE on the upper decile will look better than they should because the model never gets to be wrong by claiming p > 0.92. If the true probability for, say, BERA's setup is 0.97, we lose that 5pp signal forever.

**It also masks the "extreme conviction" tier.** A user reading the markdown report sees five different coins all labeled "92% confidence" and reasonably wonders why we can't pick the most confident one. The answer is that the calibration data couldn't distinguish them — but that's not visible from the report.

## Why fix this in v0.3, not v0.2

The most natural fix is structural rather than tactical:

1. **Extend the fit window** beyond 60 days. The upper tail needs more samples. Six months of live data after v0.2 ships will help here automatically.
2. **Switch isotonic for Platt** (logistic regression on direction_raw → p). Platt is parametric, so its tail is determined by the fitted slope rather than the empirical observations — it won't saturate at 0.92 just because no training point happened to disagree. Trade-off: Platt is monotonic by construction but less locally flexible.
3. **Hybrid: isotonic + linear tail extension** past the highest knot. Use isotonic in the body where data is rich, extrapolate linearly toward 1.0 in the tail. Cheap to implement but has a "where does the body end" knob.
4. **Beta-binomial smoothing** of the isotonic knot values themselves. Pulls each bin's y toward the prior (e.g., 0.5) by an effective-sample-size factor. Reduces upper-tail overconfidence even with limited data.

None of these are emergency fixes. The current behavior is conservative (underestimating top-tier confidence is safer than overestimating it), the ranking still works, and we now have visibility into the artifact. Logging it for v0.3 (LightGBM ML upgrade also wants to revisit calibration), with the candidate fixes above as the menu.

## Operational implications

1. **Report layer**: consider showing the calibration-ceiling badge in the markdown report whenever a coin is at the ceiling — `BERA p=0.92*` with footnote "calibration ceiling reached; ranking by |er|". Prevents user confusion about why "the most confident pick" isn't obvious.
2. **Validation diff watch**: when the validator runs and these 5 close, the realized accuracy of the 0.9198 bucket is the directly observable empirical ceiling. If it comes back at 4/5 or 5/5, the 91.98% number is approximately correct. If 2/5 or 3/5, the calibration is genuinely overconfident at the top and the fix becomes more urgent.
3. **Recalibration**: the `_job_recalibrate` cron only fires monthly on the 1st. The next opportunity to re-fit with the expanded window is 2026-07-01. Drift detection in the interim won't catch this since the symptom is not drift but stagnation.

## Watch list for the 11:30 UTC validation

When `_job_validate_pending` closes the five ceiling-hit predictions tomorrow:
- All 5 correct → 100% on the 0.92 bucket. Ceiling appears under-confident.
- 4 of 5 correct → 80% on the 0.92 bucket. Ceiling appears under-confident.
- 3 of 5 correct → 60%. Ceiling appears about right or slightly over-confident.
- ≤2 of 5 correct → ceiling is materially over-confident. Fast-track v0.3 calibration revision.
