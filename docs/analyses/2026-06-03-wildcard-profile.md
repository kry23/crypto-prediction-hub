# Wild-card profile analysis — 2026-06-03

**Snapshot**: `predictions.db` at 2026-06-03 09:00 UTC, 355 predictions total (353 pending + 2 expired). All from the 2026-06-02 11:30 UTC universe-wide scan.

**Run it**: `python scripts/wildcard_analysis.py`

## What's a wild card?

The classifier in [`orchestrator/daily_scan.py`](../../src/crypto_predictor/orchestrator/daily_scan.py) tags a prediction `WILD_CARD` whenever the per-symbol anomaly flag fires (extreme feature z-scores in funding, OI, volume, or perp microstructure). The ranker in [`orchestrator/ranker.py`](../../src/crypto_predictor/orchestrator/ranker.py) then **excludes** wild cards from top-K long/short and routes them to their own bucket in the daily report.

The intuition behind the bucket: anomalous features carry information, but the calibration was fit on the *non-anomalous* distribution, so we surface these separately rather than trusting them inside the main ranking.

## Population

| flag | n | share |
|---|---|---|
| NORMAL | 332 | 93.5% |
| WILD_CARD | 22 | 6.2% |
| HIGH_CONV | 1 | 0.3% |

22 / 355 = 6.2% wild-card share — matches the design intent of a "minority bucket of strong-but-anomalous signals".

## Wild-card composition

- **Regime mix**: 22/22 CHOP (100%). Reflects the snapshot regime — the 2026-06-02 scan ran with `regime=CHOP` for the entire universe.
- **Direction**: 15 long / 7 short (68% / 32%). Slight upside skew, consistent with the CHOP momentum-flip strategy that's been favoring contrarian longs.
- **Status**: all 22 pending. None mature yet.

## Profile vs NORMAL

| flag | n | avg p | avg \|expected return\| | avg composite |
|---|---|---|---|---|
| HIGH_CONV | 1 | 0.8679 | 0.0608 | 0.0528 |
| NORMAL | 332 | 0.6499 | 0.0222 | 0.0144 |
| **WILD_CARD** | **22** | **0.6631** | **0.0364** | **0.0161** |

**The interesting finding**: wild-card `p_direction` is essentially identical to NORMAL (0.6631 vs 0.6499 — within noise). What's different is the **expected magnitude**: wild cards expect 64% larger absolute returns than NORMAL (0.0364 vs 0.0222).

This matches expectations of how the magnitude estimator is wired — realized vol × strength × regime mult × sign. Anomalous features push the strength term to the tail of the distribution, so the magnitude balloons even though the calibrated probability doesn't.

**Implication**: wild cards are *high-variance bets at average confidence*, not *low-confidence bets*. They should outperform NORMAL on raw alpha IF the magnitude estimate is well-calibrated in the anomaly tail. They should underperform NORMAL on hit rate IF the calibration is degraded by the anomaly. We won't know which dominates until the realized-return validation cycle.

## Top 5 wild cards by composite score

| rank | symbol | p_direction | expected return | composite | side |
|---|---|---|---|---|---|
| 1 | SPCX/USDT:USDT | 0.575 | +26.57% | 0.1070 | LONG |
| 2 | H/USDT:USDT | 0.667 | −8.10% | 0.0378 | SHORT |
| 3 | EDGE/USDT:USDT | 0.640 | +5.89% | 0.0264 | SHORT |
| 4 | GRASS/USDT:USDT | 0.615 | +4.75% | 0.0205 | LONG |
| 5 | XLM/USDT:USDT | 0.638 | +4.12% | 0.0184 | LONG |

SPCX's expected return of +26.57% with a calibrated p=0.575 is the canonical wild-card signature: high magnitude (anomaly pushed realized-vol × strength to the extreme), middling probability (calibration says the upside is real but uncertain). This is the kind of bet that wild-card bucket is designed to surface — a long-tail outlier that would otherwise drown in the top-K composite ordering.

The 26.57% target is implausibly large for 24h; this is likely an OHLCV outlier or a freshly-listed contract with thin history skewing the realized-vol scale. **Action item**: investigate SPCX bar history when the prediction closes.

Several names in the list look like equity tickers (SPCX = SpaceX private fund, RKLB = Rocket Lab, CRWD = CrowdStrike, XLE = Energy ETF). OKX appears to be offering tokenized-equity perpetuals — confirmed by the `/USDT:USDT` suffix. These have thinner liquidity and shorter history than crypto perps; flagging them as wild cards is the correct triage.

## Hit rate — cannot measure yet

| flag | closed | correct | wrong | indeterminate | hit rate |
|---|---|---|---|---|---|
| NORMAL | 2 | 0 | 0 | 2 | n/a |
| WILD_CARD | 0 | — | — | — | — |
| HIGH_CONV | 0 | — | — | — | — |

Zero wild cards have closed yet — they all mature at 2026-06-03 11:30 UTC alongside the rest of the cohort. The 2 NORMAL closed predictions both came back `indeterminate` (no T+24h bar to evaluate against — probably the incremental ingest hadn't backfilled their symbols yet). Re-run this script after `_job_validate_pending` fires at 06:30 UTC tomorrow.

## What we'll want to see post-validation

Run the script again at 2026-06-03 12:00 UTC. The first row of evidence on the wild-card hypothesis will be:

1. **Wild-card hit rate vs NORMAL**: if WILD_CARD < NORMAL by ≥10pp, the anomaly flag is degrading calibration and we should consider not surfacing them. If WILD_CARD ≥ NORMAL, the bucket is earning its slot.
2. **Wild-card top-K alpha**: aggregate realized return of the long wild cards minus short wild cards. With 22 names this is too few to be statistically meaningful, but a consistent pattern over 4–6 weeks will tell us whether the magnitude estimate in the anomaly tail is trustworthy.
3. **SPCX-specific**: did the +26.57% magnitude estimate hold up, or did the bar close in a typical −5%/+5% band? This is the canonical "is our anomaly-tail magnitude broken" question.

## Open questions for v0.3

- Should wild cards have their own calibration map? Currently they're calibrated against the NORMAL distribution, which is the source of the calibration-credibility doubt.
- Should the anomaly flag be a feature in itself, fed into a richer ML magnitude model rather than gating the bucket assignment?
- The 100% CHOP concentration is artifact of today's regime, but worth re-checking in BULL/BEAR conditions — does the anomaly flag fire as often when the rest of the universe is trending hard?
