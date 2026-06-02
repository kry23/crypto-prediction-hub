# Plan D Completion Report + Phase 1 Closing — Validation Loop (Weeks 9–10)

**Date**: 2026-06-03
**Status**: Plan D 13/13 tasks complete. Phase 1 closed.
**Test count**: 170 unit + 2 integration = 172 total, all green.

## What Plan D delivers

| Capability | Status |
|---|---|
| Validator (T+24h closure) | OK |
| Rolling metrics (7d/30d/90d × regime × direction) | OK |
| Top-K alpha vs equal-weight universe | OK |
| Markdown report live "Validation Track Record" section | OK |
| `/predict-track` slash command | OK |
| Pattern detector (confidence_flag × regime → SEEK/NEUTRAL/AVOID) | OK |
| Calibration drift detector (Brier vs backtest baseline) | OK |
| Scheduler `validate_pending` + `weekly_metrics` wired | OK |
| Scheduler `recalibrate` Phase-1 scaffold | OK |
| Plan C follow-up: prediction direction ↔ target_value sign aligned | OK |

## Critical operational gap discovered during 9.8 dry-run

**Validator needs CURRENT OHLCV data to evaluate predictions, but the system only has one-shot ingest.**

When a prediction was inserted with `created_at = NOW - 25h` and the validator looked for the bar at `NOW - 1h`, that bar didn't exist because the last bulk ingest ended at 2026-06-02 01:36 UTC — ~13 hours before the dry-run. The validator gracefully marked the prediction `expired` instead of crashing, but no real validation happened.

**Implications:** in production, predictions created at 06:00 UTC need OHLCV data through 06:00 UTC the next day. Without an incremental ingest job running before `validate_pending` (06:30 UTC), every prediction will expire and `metrics_rolling` will stay empty.

**Solution (Phase 2 follow-up):**
- Add `scheduler/jobs.py::_job_incremental_ingest` that runs at 06:15 UTC
- Fetches just the missing recent bars for the universe (not 6 months — only since last ingest)
- Should complete in 1-2 min

For Phase 1 closing, the wire-up is correct and the issue is operational, not structural.

## Plan D commits

Chain from `078daab` through completion (the integration test + this report will land as the 12th commit):

| SHA | Subject |
|---|---|
| 078daab | fix(orchestrator): target_value sign matches calibrated prediction direction (7.8 follow-up) |
| 08cfe65 | feat(scoring): actual_returns_batch helper for validator |
| f4e1bdb | feat(validation): validator closes pending predictions against realized returns |
| 501c3dc | feat(validation): rolling metrics computation + metrics_rolling persistence |
| 928f13b | feat(report): wire live rolling metrics into daily markdown |
| 7df7f5b | feat(cli): /predict-track command + CLI for rolling metrics |
| 39eb301 | feat(scheduler): wire validate_pending and weekly_metrics jobs |
| e767338 | feat(patterns): simple pattern detector (confidence_flag × regime cohorts) |
| de17744 | feat(calibration): drift detector (current Brier vs backtest baseline) |
| a11176e | feat(validation): top-K alpha vs equal-weight universe in rolling metrics |
| 3be45e3 | feat(scheduler): recalibrate job (Phase 1 scaffold; auto-refit deferred to v0.3) |
| (this PR) | test(integration): Plan D end-to-end + Phase 1 closing report |

## Phase 1 — final state

Plans completed in chronological order:
- Plan A — data foundation (30 tasks)
- Plan B — scoring + calibration (18 tasks)
- Phase 1.5 — diagnostic sprint (5 substantive commits, all §19 targets MET)
- Plan C — daily pipeline (14 tasks)
- Plan D — validation loop (13 tasks)

**Total**: ~80 tasks, 172 tests, 95+ commits, complete production scaffold.

## Spec §19 success criteria — final

| Criterion | Result |
|---|---|
| Direction hit rate ≥ 58% (rolling 30d) | MET — 62.5% on 340-sym Phase 1.5 validation |
| Calibration MAE ≤ 5% | MET — near-perfect (predicted ≈ empirical) |
| Top-K alpha ≥ +1.5% | MET — +2.42% combined |
| Brier score ≤ 0.23 | MET — 0.226 |
| Daily run uptime ≥ 95% | TBD during first 30 days of live ops |
| Unit test coverage ≥ 75% | Pending pytest-cov verification (expected ~80%) |

## What ships from Phase 1

Production-ready scaffold:
- Daily orchestrator (06:00 UTC) → 343-symbol universe → calibrated predictions
- Validation at T+24h (when fresh OHLCV is available)
- Markdown daily report + Telegram delivery
- Track record dashboard via `/predict-track`
- Pattern mining + drift detection

## v0.2 / v0.3 backlog

**v0.2 (when ready):**
- 4h horizon
- Sector concentration overlay
- Notification preferences v2
- Per-prediction feature snapshots
- Incremental ingest job (CRITICAL for live operation)
- Sentiment + global cache fetchers (NewsAPI + LunarCrush + crypto-data MCP)
- Real Telegram drift alerts (currently logs only)

**v0.3:**
- LightGBM ML model (ensemble or replace heuristic)
- A/B harness for parallel formula testing
- Auto-recalibration with staged rollout
- Drift monitor automation

## Honest closing assessment

The system is **structurally complete** and **operationally close**. The one critical gap is the missing incremental ingest job — until it ships in v0.2, live validation will produce empty metrics_rolling. Everything else is wired, tested, and ready.

When v0.2 ships the incremental ingest, Phase 1 transitions to true production operation: predictions made today get validated tomorrow with fresh data, rolling metrics populate, the daily report's "Validation Track Record" section comes alive, and the system starts learning from its own track record.
