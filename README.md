# crypto-predictor

Heuristic-first probabilistic prediction platform for OKX-Global USDT perpetuals. Daily 06:00 UTC universe-wide scan, calibrated direction probability + magnitude predictions, self-validating track record.

**Status**: Phase 1 complete + v0.2 production lifeline shipped. Currently awaiting first live validation cycle (~2026-06-03 11:30 UTC).

## What it does

Every day at 06:00 UTC the system:
1. Scans the full ~340-symbol OKX Global USDT-perp universe
2. Computes ~30 features per coin (momentum, perp microstructure, volume, technical, sentiment, global context)
3. Applies a per-regime data-driven heuristic to produce calibrated P(↑) + expected return
4. Ranks top-20 long + top-20 short candidates + wild cards (anomaly-flagged)
5. Persists every prediction to `predictions.db` (status='pending')
6. Renders a markdown daily report → `reports/predict-YYYY-MM-DD-HHMM.md`
7. Pushes compact Telegram summary + high-conviction alerts

Then 24h later, the validator closes pending predictions against realized returns, updates rolling 7d/30d/90d hit rate + top-K alpha, mines pattern cohorts, and monitors calibration drift.

## Key metrics (Phase 1.5 validation)

| Metric | Result | §19 target |
|---|---|---|
| Direction hit rate | 62.5% (340-sym) | ≥58% ✅ |
| Calibration MAE | near-perfect | ≤5% ✅ |
| Top-K alpha (combined) | +2.42% | ≥+1.5% ✅ |
| Brier score | 0.226 | ≤0.23 ✅ |

## Architecture

```
data/history/             — Parquet OHLCV + futures, 6 months × 340 perps
data/equity_blacklist.yaml — Base currencies excluded from the universe (tokenized equity perps)
predictions.db            — SQLite: predictions, predictions_features, metrics_rolling, patterns
sentiment_cache.db        — SQLite: daily news sentiment per symbol
global_cache.db           — SQLite: BTC dom + total mcap + sector indices

src/crypto_predictor/
├── data/          — OKX ccxt client + parquet store
├── features/      — 6 feature families + asof-guarded fetcher
├── scoring/       — tilts, direction (per-regime weights + CHOP momentum-flip), magnitude, regime, anomaly, composite
├── calibration/   — per-regime isotonic regression + drift detector
├── backtest/      — walk-forward runner, metrics, markdown report
├── orchestrator/  — daily scan + ranker + LLM rationale
├── output/        — markdown + Telegram formatters, threshold-based alert routing
├── validation/    — T+24h prediction closure + rolling metrics
├── patterns/      — feature-extreme cohort mining (SEEK/NEUTRAL/AVOID)
├── sentiment/     — NewsAPI fetcher (Tier 1) + LunarCrush scaffold (Tier 2)
├── global_ctx/    — CoinGecko BTC dominance fetcher
├── scheduler/     — APScheduler with 5 cron jobs
└── mcp/           — FastMCP server with ping tool
```

## Scheduler

Five cron jobs (UTC):

| Time | Job | What |
|---|---|---|
| 06:00 | `predict_scan` | Universe scan → predictions.db + markdown + Telegram |
| 06:15 | `incremental_ingest` | Fetch fresh OHLCV bars since last ingest |
| 06:30 | `validate_pending` | Close T+24h predictions against realized returns |
| Sun 07:00 | `weekly_metrics` | Refresh rolling metrics + pattern detection |
| Monthly 1st 07:00 | `recalibrate` | Drift check + Telegram alert (auto-refit deferred to v0.3) |

## Plans & history

Documented in `docs/plans/`:
- `2026-06-01-crypto-predictor-design.md` — 21-section design spec
- Plan A — data foundation (30 tasks)
- Plan B — scoring + calibration (18 tasks)
- Phase 1.5 — diagnostic sprint (5 commits, all §19 targets met)
- Plan C — daily pipeline (14 tasks)
- Plan D — validation loop (13 tasks)
- v0.2 — production lifeline (13 tasks)

Session journal: `docs/sessions/2026-06-03-full-session-journal.md`

Full changelog: `CHANGELOG.md`

## Quick start (development)

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
uv venv
uv pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -v
```

## Commands

```powershell
# Start the foreground scheduler — cron jobs only fire while this process is alive
.\.venv\Scripts\python.exe scripts\run_scheduler.py

# Trigger daily scan manually
.\.venv\Scripts\python.exe scripts\predict_scan_cli.py

# Close mature predictions on demand (does not wait for 06:30 cron)
.\.venv\Scripts\python.exe scripts\validate_pending_cli.py

# Show rolling track record
.\.venv\Scripts\python.exe scripts\predict_track_cli.py

# Re-run backtest
.\.venv\Scripts\python.exe scripts\run_backtest.py --start 2026-01-01 --end 2026-05-31

# Incremental ingest (manual)
.\.venv\Scripts\python.exe scripts\incremental_ingest.py --root data\history
```

> **Important**: the scheduled cron jobs (06:00 predict scan, 06:15 ingest, 06:30
> validate, 06:45 backup, weekly metrics, monthly recalibrate) fire only while
> `run_scheduler.py` is alive. For unattended operation, wire it under Windows Task
> Scheduler ("At log on" trigger) or `nssm`. Without a runner, all daily cadence
> must be triggered manually via the CLIs above.

## Scheduler config

The runtime mode and active calibration version live in
`data/scheduler_config.yaml`. Defaults are `mode: shadow` and
`calibration_version: 1_5_4`. Edit the file and restart
`scripts/run_scheduler.py` to apply changes.
A `.example` is at `data/scheduler_config.yaml.example`.

**Shadow mode** means: the scheduler runs predict + validate + backup
exactly as in live mode, but predictions are persisted with `mode='shadow'`,
the markdown report H1 reads `🔬 Crypto Predictor — SHADOW Daily Report`,
and the post-validation Telegram digest is prefixed `🔬 Shadow validation`.
No live alert is sent under shadow.

To fully silence Telegram during shadow runs, set
`shadow_skip_telegram: true` in the yaml. Scan-start heartbeat and the
post-validation digest are then suppressed entirely.

`git diff` on this file = audit trail of mode and calibration version flips.

## Secrets

Copy `data/secrets.env.example` → `data/secrets.env` and fill in:
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — for daily summary + drift alerts
- `NEWSAPI_API_KEY` — Tier-1 sentiment (free tier sufficient for top-30 mcap)
- `LUNARCRUSH_API_KEY` — Tier-2 social (paid, optional)
- `ANTHROPIC_API_KEY` — LLM rationale (optional; falls back to structured one-liner)

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

191 tests as of v0.2 ship: ~186 unit + 7 integration (Plan A/B/C/D + v0.2 each have integration tests against real BTC data).

## License

MIT
