# Changelog

All notable changes to crypto-predictor are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) loosely.

## [Unreleased — v0.2 polish]

### Infrastructure
- **2026-06-05/06 — Cutover to cloud (Hostinger KVM VPS, `krypredictor.com`)**. Migrated the scheduler + data + UI off the laptop-bound Windows Task Scheduler onto an always-on Ubuntu 24.04 box: PostgreSQL 16, systemd units (scheduler + ui + intel-bridge + cloudflared), Cloudflare Tunnel. SQLite→PG data migration preserved all shadow rows (684) — the v0.3 14-day clock kept ticking through the move.
  - Auth: Cloudflare Access (Zero Trust) requires a billable payment method, so the UI is gated by **nginx basic-auth** behind the tunnel instead (`tunnel → nginx:80 → streamlit:8501`). Zero-cost, no Zero Trust dependency.
  - Secrets: single `/etc/crypto-predictor/secrets.env`; `data/secrets.env` is a symlink to it so both `load_secrets()` (file read) and systemd `EnvironmentFile=` see one source.
- `29a7697` — **SQLite→PG sync bridge** (`scripts/sync_sqlite_to_pg.py` + systemd timer, every 10 min). The pipeline still writes SQLite; the UI reads PG. The bridge UPSERTs so validation status changes propagate (not just inserts). Interim until the pipeline is converted to PG natively (planned v1.1).

### Fixed
- `8ebbc52` — NewsAPI fetcher: ISO datetime `from` param returns 0 articles; switched to `YYYY-MM-DD` format. Sentiment cache now actually populates on daily scan when `NEWSAPI_API_KEY` is set.

## [v0.2] — 2026-06-03 — "Production Lifeline"

### Added
- **Phase 2A — operational lifeline (gating fix)**
  - `5773c8b` — Incremental OHLCV + futures fetcher (`scripts/incremental_ingest.py`)
  - `f03ace7` — Scheduler `_job_incremental_ingest` wired at 06:15 UTC (between predict_scan and validate_pending)
  - First live incremental run: 286,594 new bars in 22 min (340 sym × ~30h gap)
- **Phase 2B — sentiment + global cache resurrection**
  - `6422159` — NewsAPI fetcher (Tier 1 top-30 mcap) + cache writer + LunarCrush scaffold
  - `f8196c6` — CoinGecko BTC dominance fetcher + cache writer (free tier)
  - `a418c29` — Sentiment + global fetchers wired into `_job_predict_scan`
- **Phase 2C — feedback enrichment**
  - `6a62378` — Per-prediction feature snapshots persisted to `predictions_features` table
  - `574fe8f` — Pattern detector v2 (feature-extreme cohort mining, POS/NEG by |z| threshold)
  - `08f1e93` — Calibration drift detector wired to Telegram alert in `_job_recalibrate`
- **Phase 2D — closing**
  - `a1addfe` — v0.2 integration test (5 new) + completion report

### Pending
- Task 11.3 closure — validator on 353 real predictions, waiting for natural maturity at ~2026-06-03 11:30 UTC
- Task 11.4 — first live hit-rate observation doc

### Stats
- 191 tests (186 unit + 7 integration) — all green
- 10 v0.2 commits

## [v1.0-rc] — 2026-06-03 — "Phase 1 Closed"

Phase 1 = Plan A + Plan B + Phase 1.5 + Plan C + Plan D.

### Plan D — Validation Loop (Weeks 9–10)

#### Added
- `validation.validator.validate_pending_predictions` — closes pending predictions at T+24h
- `validation.rolling_metrics.update_rolling_metrics` — 7d/30d/90d × regime × direction aggregation
- `validation.rolling_metrics.compute_top_k_alpha` — top-K alpha vs equal-weight universe
- `patterns.pattern_detector.detect_and_upsert_patterns` — (confidence_flag × regime) cohort mining
- `calibration.drift.detect_drift` + `DriftStatus` enum
- `scheduler._job_validate_pending`, `_job_weekly_metrics`, `_job_recalibrate` (Phase 1 scaffold)
- `/predict-track` slash command + `scripts/predict_track_cli.py`
- Markdown daily report wired to live rolling metrics

#### Fixed
- `078daab` — `target_value` sign now matches calibrated prediction direction (was off when calibration flipped sign)

### Plan C — Daily Pipeline (Weeks 7–8)

#### Added
- `orchestrator.daily_scan.run_daily_scan` — full universe scan + predictions persistence
- `orchestrator.ranker.rank_predictions` — top-K long/short + wild cards
- `orchestrator.llm_summary.generate_rationale` — Claude Haiku rationale with safe fallback
- `output.markdown_report.render_daily_report` — §15.1 layout
- `output.telegram_summary.render_telegram_summary` + `render_high_conviction_alert`
- `output.telegram_delivery.send_message` — Bot API via httpx
- `output.thresholds` — alert routing config + classifier
- `scheduler._job_predict_scan` wired to write report + send Telegram
- `/predict-scan` slash command + `scripts/predict_scan_cli.py`

### Phase 1.5 — Diagnostic Sprint

#### Fixed
- `e27701e` — short alpha was hardcoded `0` in runner.py. Properly bidirectional ranking → combined alpha jumped −0.47% → +1.62%.
- `93b87a1` — data-driven weights from per-tilt correlation analysis + CHOP momentum sign-flip → hit rate 56.6% → 62.7%, all §19 targets met
- `MOMENTUM_FLIP_BY_REGIME = {"BULL": +1, "CHOP": -1, "BEAR": +1}` — empirical: momentum is mean-reverting in chop

### Plan B — Modeling (Weeks 4–6)

#### Added
- 6 tilt functions (momentum, perp, volume, technical, sentiment, global)
- `compute_direction_raw` + `compute_direction_raw_for_regime`
- Magnitude estimator (realized vol × strength × regime mult × sign)
- Regime detector (BULL/BEAR/CHOP voting)
- Anomaly flag + composite score
- Walk-forward backtest framework
- Per-regime isotonic calibration + JSON persistence
- Backtest metrics module + markdown report renderer
- `scripts/run_backtest.py` CLI

### Plan A — Foundation (Weeks 1–3)

#### Added
- Plugin scaffold (`pyproject.toml`, `.claude-plugin/{plugin,marketplace}.json`)
- 7-table `predictions.db` schema + `features.db` cache
- FastMCP server (ping tool)
- APScheduler skeleton
- structlog JSON logging + secrets loader
- Bulk OHLCV + futures ingest (340 perps × 6 months × 4 timeframes = 2,408 parquets in 2h42m)
- FeatureFetcher with strict asof guard
- 6 feature families + sector classifier + mcap_rank_weight
- `compute_features()` orchestrator (~30 features in <500ms)

#### Fixed (caught during execution)
- `261761e` — `safe_symbol()` sanitizes ccxt unified symbols (`/` and `:`) for Windows paths
- `b800482` — `ccxt_to_okx_instid/uly/base_ccy` converters for OKX public endpoints; `fetch_long_short_ratio` array-shape parser; `fetch_liquidations` uses `uly` + `state=filled`
- `674077e` — `fetch_oi_history` uses `openInterestValue` field (not `openInterestAmount` which OKX returns as null); `perp.py` null-guard for legacy parquets

---

## Notes on versioning

We're using semantic versioning loosely:
- **v1.0** will be tagged once first live hit rate confirms ≥ Phase 1.5 backtest baseline (62.5% over 7 days)
- **v0.x** patches ship as bug fixes / small enhancements between minor releases
- **v0.3** = LightGBM ML upgrade (Q3 2026 target)
- **v0.4+** = sentiment vocabulary v2, 4h horizon, sector overlay, etc.
