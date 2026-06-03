# First live observation — 2026-06-03

**Cohort**: 353 predictions created 2026-06-02 11:30 UTC, matured 2026-06-03 11:30 UTC, closed manually at 2026-06-03 12:35 UTC after a data-recovery cycle.
**Result snapshot**: 329 evaluable, 26 expired (no T+24h bar for thin-history names).

## Headline

| metric | live | backtest baseline | delta | verdict |
|---|---|---|---|---|
| hit rate | **32.8%** | 62.5% | **−29.7pp** | catastrophic miss |
| Brier | **0.346** | 0.226 | +0.120 | calibration badly broken |
| top-K up | 12.5% | — | — | model was bullish in a bearish day |
| top-K down | 56.2% | — | — | shorts did fine |

Two days of backtest validation said this system would hit 62.5%; first live cohort came in at 32.8% — well below coin-flip 50%.

## By direction

| direction | n | correct | hit rate |
|---|---|---|---|
| up | 176 | 22 | **12.5%** |
| down | 153 | 86 | 56.2% |

This is the largest single signal. The system was overwhelmingly bullish (176 longs vs 153 shorts) on a day when most altcoins fell. BTC went from $67,548 → $67,014 (−0.79%), but the broader alt complex dropped harder — BERA −9.9%, SAND −3.6%, SOL/AVAX/SUI similar. The model's contrarian-long bias (CHOP momentum-flip from Phase 1.5) was exactly wrong for this regime.

## Calibration by probability bucket

| p_direction bucket | n | correct | realized hit rate | expected (mean p) | delta |
|---|---|---|---|---|---|
| [0.50, 0.55) | 15 | 11 | 73.3% | 53.8% | +19.5pp |
| [0.55, 0.60) | 38 | 9 | **23.7%** | 57.7% | −34.0pp |
| [0.60, 0.65) | 187 | 79 | 42.2% | 63.4% | −21.2pp |
| [0.65, 0.70) | 10 | 3 | 30.0% | 69.1% | −39.1pp |
| [0.70, 0.75) | 64 | 5 | **7.8%** | 73.3% | −65.5pp |
| [0.75, 0.80) | 7 | 0 | **0.0%** | 76.7% | −76.7pp |
| [0.80, 0.95) | 8 | 1 | 12.5% | 89.2% | −76.7pp |

**Higher confidence = worse performance.** The system is anti-calibrated above p = 0.55. The lowest-confidence bucket (15 names at ~54%) did best (73%). The two highest-confidence buckets, where the daily report's headline picks come from, returned 0% and 12.5% respectively.

This is exactly the failure mode the calibration-ceiling analysis (`docs/analyses/2026-06-03-calibration-ceiling.md`) warned about: the isotonic ceiling at 0.9198 was not "conservative" — it was *underestimating overconfidence*. The model thinks it knows; it doesn't.

## Ceiling-hit watch list — VERDICT

Today's call from §19.5: "if ≤2 of 5 ceiling-hit predictions are correct → calibration is materially over-confident, fast-track v0.3 revision".

| coin | predicted | actual | result |
|---|---|---|---|
| BERA/USDT:USDT | +2.55% up | −9.93% | wrong |
| CELO/USDT:USDT | +2.15% up | −1.55% | wrong |
| ATOM/USDT:USDT | +1.82% up | +0.95% | **correct** |
| SAND/USDT:USDT | +1.79% up | −3.57% | wrong |
| DOOD/USDT:USDT | +2.23% up | −6.16% | wrong |

**1 of 5 correct = 20%, well under the 2-of-5 threshold.** v0.3 calibration revision is now urgent, not aspirational.

## SPCX wild card — magnitude estimator confirmed broken

§19.4 hypothesis: "SPCX +26.57% magnitude is almost certainly an OHLCV outlier or thin-history skew. Watch when it closes."

Result: predicted +26.57% up; actual **−5.54%**. The realized-vol × strength magnitude estimator hit by a clean ×6 error in the direction-inverted tail. The anomaly-flag bucket is not just miscalibrated on probability — its magnitude estimator is also unreliable for these tokenized-equity / thin-history symbols.

Recommendation: filter `SPCX`, `RKLB`, `CRWD`, `XLE` (and any other ticker pattern that maps to a US equity) out of the universe pending a separate magnitude calibration for that subspace. Track via a `data/equity_blacklist.yaml`.

## Wild-card vs NORMAL post-validation

| flag | n | correct | hit rate |
|---|---|---|---|
| HIGH_CONV | 1 | 0 | 0.0% |
| NORMAL | 307 | 101 | 32.9% |
| WILD_CARD | 21 | 7 | 33.3% |

Wild cards came in at **33.3%**, essentially identical to NORMAL's 32.9%. So under §19.4's hypothesis ("if WILD_CARD < NORMAL by ≥10pp the anomaly flag is degrading calibration"), the bucket is *not* dragging things down on this one cohort — but the population is way too small (21 names, one day) for a definitive call. Re-evaluate after 7 days.

## Compounding factors — why the live miss was this bad

1. **All features were running with NEUTRAL sentiment**. The sentiment_cache.db that v0.2 was supposed to populate didn't exist at the time of the 11:30 UTC scan. The NewsAPI date-format bug (§19.1, fixed in `8ebbc52`) shipped after the scan ran, so the cache was never written. The model used `news_sent_24h=0, social_sent_24h=0, sent_velocity=0, news_volume_z=0` for every prediction. One of the six tilts was silently zero.

2. **Global context also NEUTRAL**. `global_cache.db` had been created but `btc_dom_trend_7d`, `eth_btc_trend_7d`, `total_mcap_z` were all hardcoded to 0.0 (the very stub Task 1 of §19.9 fixed *after* the scan ran). The cross-coin tilt had no signal.

3. **All-CHOP regime**. The backtest training distribution had ~50% BULL, ~30% CHOP, ~20% BEAR. Live was 100% CHOP, where the model's per-regime weights are most stressed.

4. **CHOP momentum-flip in the wrong direction**. The Phase 1.5 weights apply `MOMENTUM_FLIP_BY_REGIME["CHOP"] = -1` — mean-reversion expectation. The 24h window was clearly trending-down (not chopping), so the contrarian long bias amplified the miss.

5. **Tokenized equity perps in the universe**. SPCX/RKLB/CRWD/XLE didn't exist in backtest data; their thin history broke the realized-vol-based magnitude estimator.

Any one of these alone would have hurt; all five together produced the 30pp gap.

## What the system did right

Despite the catastrophe, two pieces worked:
- **Telegram digest landed automatically** post-validation (§19.7 wiring). The user got the hit-rate/Brier/breakdown in one Telegram message without needing to be at a console.
- **Per-bucket calibration check confirmed broken-ness explicitly**. We're not guessing; we have a 76.7pp gap in the [0.80, 0.95) bucket as a concrete number. v0.3 calibration revision has a baseline.

## Recommended actions

**Immediate (before next 06:00 UTC scan, manual)**:
- Pause the morning scan OR mark calibration_1_5_4 as "do not use for live" until the next set of recommendations land. The 06:00 UTC predict_scan will produce another cohort with the same broken calibration; sending Telegram alerts on those would erode user trust.
- Populate sentiment_cache and global_cache properly before the next scan (run the cache fetchers manually, or wait until after the run_scheduler.py cycle catches up).

**Short term (this week)**:
- v0.3 calibration revision is no longer "later" — fast-track. The menu in `docs/analyses/2026-06-03-calibration-ceiling.md` (Platt, beta-binomial, hybrid, extended fit window) is now the highest-priority v0.3 work.
- Equity-perp blacklist as `data/equity_blacklist.yaml` — wire into `list_active_perps()`. SPCX/RKLB/CRWD/XLE confirmed problematic.
- Add `_job_predict_scan` precondition: skip the scan if `sentiment_cache.db` is older than 24h. Currently it runs regardless.

**Medium term**:
- Daily backtest-vs-live drift monitoring on the rolling 7d window — alert if delta exceeds 10pp.
- Per-regime hit-rate tracking — if CHOP keeps coming in below 50%, the momentum-flip sign needs a live-data re-fit, not the Phase 1.5 backtest fit.
- Per-feature-availability annotation: every prediction should carry a flag if any feature family was NEUTRAL (sentiment, global). Calibration won't recover if NEUTRAL-feature predictions are mixed with full-feature ones.

## How we knew

The full validation loop fired and surfaced this catastrophe in under 90 seconds:
1. `validate_pending_cli.py` closed 353 predictions
2. `summarize_recent_closures()` aggregated hit rate + Brier
3. `format_validation_telegram()` rendered the digest
4. Telegram delivered to user phone

The infrastructure built in Plan D + v0.2 + the pre-validation polish batch (§19.6–19.8) did exactly what it was designed to do. The model failed; the observability worked.
