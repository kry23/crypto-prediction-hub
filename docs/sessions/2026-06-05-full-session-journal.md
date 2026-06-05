# Full Session Journal — 2026-06-04 + 2026-06-05

Continues from `2026-06-03-full-session-journal.md` which ended at §19.12 (v0.2.1 shadow infrastructure shipped). This file covers two calendar days of work: persistent operation, a 10-bug audit + fix round, v0.3 calibration revision implementation (Tasks 1–10), and the v1.0 web UI + cloud migration brainstorm + spec.

---

## §20 Persistent operation — Windows Task Scheduler installer (2026-06-04, commit `36b2029`)

Day after the v0.2.1 ship, discovered the manually-started scheduler process was gone (session ended, OS killed it). The runbook said "wire under Windows Task Scheduler 'At log on'" but we never did. Wrote and ran:

- `scripts/install_windows_scheduler.ps1` — registers `CryptoPredictorScheduler` at user logon, runs the Python scheduler under PowerShell with hidden window, appends stdout/stderr to `logs/scheduler_persistent.log`. Restart on crash: 99 retries, 5-min interval.
- `scripts/uninstall_windows_scheduler.ps1` — removes the task + kills leftover processes.
- README "Persistent operation (Windows)" subsection with the four maintenance commands (start/inspect/stop/uninstall).

Verified live: task started, two python.exe processes (powershell wrapper + Python child), `scheduler_persistent.log` shows `scheduler_running` event with all 6 cron jobs + `timezone: UTC`.

**Caveat**: This is the laptop-bound deployment. The next session (today, 2026-06-05) brainstormed the cloud migration spec to escape this constraint entirely.

---

## §21 Bug audit + 10 fixes (2026-06-04, commits `7660095`..`0a549a3`)

Found that the overnight scheduler ran but produced **zero shadow predictions**. Cascading audit uncovered ten bugs that pytest didn't catch. Dispatched a code-review subagent for breadth, fixed sequentially.

### §21.1 Critical batch (commit `7660095`, then `6bb785e`)

1. **`misfire_grace_time` default 1s** — APScheduler woke 3.88s late for the 06:00 predict_scan and silently dropped it. Fix: `misfire_grace_time=3600 + coalesce=True` on every `add_job`.
2. **`CronTrigger` timezone not inherited from BackgroundScheduler on Windows** — incremental_ingest and validate_pending fired in Turkey local time (UTC+3) instead of UTC. Fix: explicit `timezone="UTC"` on each `CronTrigger`.
3. **`calibration_version` silently overwritten in `run_daily_scan`** — the kwarg passed from `run_full_scan` was shadowed by `calibration_path.stem`, so the persisted column read `"calibration_1_5_4"` instead of the config's `"1_5_4"`. Fix: trust the kwarg; stem fallback only when caller didn't pass one.
4. **`detect_feature_completeness` always returned `'degraded'`** — `_is_all_neutral(None)` returned True, so passing `sentiment_features=None` (which `run_full_scan` does as the file-existence-only approximation) marked every cohort `degraded`. Fix: `None` means "use file-existence only", not "all-neutral". A populated dict of all-zero values still counts as missing.
5. **`scripts/predict_scan_cli.py` sys.path crash** — same `ModuleNotFoundError: scripts.backup_databases` that `run_scheduler.py` fixed earlier. Same fix pattern: inject project root into `sys.path` at the top of the script.
6. **`send_message` inner-import shadowing** — `_job_predict_scan` had `from crypto_predictor.output.telegram_delivery import send_message` inside the function. Python parsed `send_message` as a local variable for the WHOLE function scope, so the earlier scan-start heartbeat raised `UnboundLocalError` before line 191 ran. Fix: remove the inner import, rely on the module-level one. Same trap that bit `load_secrets` in Task 10 of v0.2.1.

Four new guard tests added: `test_all_triggers_use_utc_timezone`, `test_all_jobs_have_misfire_grace_time`, `test_all_jobs_coalesce_backlog`, `test_files_present_with_none_dicts_returns_full`. Suite 277 → 281.

### §21.2 Polish batch (commit `9093091`)

7. **`httpx.Client` leak on exception** — both sentiment-fetch and global-fetch blocks reorganized to `with _httpx.Client(...) as ...:` so the client closes even if a fetcher raises.
8. **3× `datetime.now()` consolidated** — sentiment cache row, run_full_scan persistence, and output delivery now share one `asof` defined at the top of `_job_predict_scan`. Previously the three calls could drift seconds apart; `_load_predictions` in `run.py` used exact-match on `created_at`, so any drift could silently return zero rows.
9. **SQLite `'-7 days'` now explicit UTC** — `_job_recalibrate` compared `validated_at` (stored as `+00:00` ISO) against `datetime('now', '-7 days')` which was server local time. Off by host TZ offset on non-UTC machines. Now `datetime('now', 'utc', '-7 days')`.
10. **Strict YAML bool parsing** — `shadow_skip_telegram: 'false'` (quoted string) was truthy under `bool()`, silently turning OFF Telegram when the user wanted it ON. New `_strict_bool` accepts only Python bools and known truthy/falsy string tokens; unrecognized values raise.

Suite 281 → 284.

### §21.3 Round 3 — mcap_ranks gap (commit `0a549a3`)

Live cohort came back `feature_completeness='degraded', missing_features='sentiment'`. Root cause: `data/mcap_ranks.yaml` never existed → `mcap_map = {}` → every symbol's rank was None → `top_symbols = [(s, r) for ... if r is not None][:30]` collapsed to `[]` → NewsAPI loop ran zero times → sentiment_cache.db never created → next scan's completeness check saw missing cache → `degraded`. No log told us why.

Fixes:
- `scripts/generate_mcap_ranks.py` — fetches CoinGecko top-250 markets, writes `data/mcap_ranks.yaml` as `{BASE_CCY: rank}`. 5 unit tests.
- `jobs.py` emits `log.warning("mcap_ranks_missing", hint=...)` when the file is absent. No more silent fallback.
- `_load_predictions` tolerance window (`asof ± 60s`) instead of exact-match — defensive against future re-introduction of datetime drift.

Verified end-to-end after fix: `generate_mcap_ranks` wrote 250 entries; manual scan completed with `completeness='full', missing_features=null`, 342 predictions persisted; `sentiment_cache.db` populated with 30 rows of real NewsAPI sentiment (BTC −0.30, ETH −0.17, LINK +0.07 — bearish tone).

Suite 284 → 289.

### §21.4 v0.3-prep diagnostic — `shadow_status.py` (commit `534b002`)

Quick CLI report on shadow data accumulation, intended for daily use during the dormant window:
- Total / pending / closed counts with rolling hit rate
- Breakdown by `feature_completeness` (full vs degraded), regime, calibration_version
- Date range + day count vs the 14-day v0.3 ship target

Live verify: 684 shadow rows (1 day, mix of degraded and full from the mcap_ranks bootstrap), 0 closed, 1/14 days.

Suite 289 → 296.

---

## §22 v0.3 calibration revision shipped (2026-06-05, commits `ced7a04`..`d54b025`)

User's call: "use the dormant 13 days productively, ship all v0.3 code now against synthetic data so Day-14 is just the final scripts against real shadow data."

Subagent-driven execution against the plan at `docs/superpowers/plans/2026-06-03-v0.3-calibration-revision.md`. Same pattern as v0.2.1 — one implementer dispatch per task, controller diff-reviews + runs the test slice + commits, continuous.

### §22.1 Math foundation (Tasks 1–3)

- **Task 1 — Beta-binomial smoothing** (commit `ced7a04`, 6 tests). `smooth_isotonic_knots(x, y, n_per_knot, prior_alpha, prior_beta)`. `y_smooth = (n*y + alpha) / (n + alpha + beta)`. Pulls each knot toward the Beta(α, β) prior mean by effective sample size. Beta(1, 1) default pulls toward 0.5.
- **Task 2 — Linear tail extrapolation** (commit `dfc1008`, 5 tests). `extrapolate_upper_tail(x, y, target_x, cap)`. Linear extension past the highest knot using the slope of the last two knots, capped at 1.0.
- **Task 3 — Combined runtime pipeline** (commit `e39cce9`, 6 tests). `fit_smoothed_isotonic` does the critical math: fit isotonic → extract knots + per-knot n → smooth → **re-fit weighted IsotonicRegression** to restore monotonicity (smoothing alone can break it when low-n knots get pulled below their high-n neighbors). `apply_calibrated_lookup` is the runtime: in-domain linear interpolation, out-of-domain tail extrapolation.

### §22.2 Storage + scripts (Tasks 4–7)

- **Task 4 — Per-completeness calibration storage** (commit `029efcc`, 7 tests). `PerCompletenessCalibration` dataclass + `save_per_completeness` / `load_per_completeness` JSON round-trip + `lookup_calibrated_probability` with two-stage fallback: `(completeness, regime)` → `('full', regime)` → KeyError. Covers the spec-acknowledged BEAR sparse-sample risk.
- **Task 5 — `refit_calibration_v03.py`** (commit `91aaf62`, 4 tests). The Day-14 calibration entry point. `weighted_concat(backtest, shadow, shadow_weight)` (default shadow_weight=3); `fit_per_completeness_calibration` skips groups under `MIN_SAMPLES_PER_FIT=30` with audit log; `load_predictions_for_fit` reads SQLite. CLI: `--shadow-weight --prior-alpha --prior-beta`.
- **Task 6 — `refit_tilt_weights_v03.py`** (commit `329d5d7`, 4 tests). Per-tilt × per-regime correlation refit with sign-flip audit. `detect_sign_changes` flags any tilt whose new correlation flips sign vs Phase 1.5 weights AND `|corr| > 0.05`. Output YAML includes weights + `sign_changes` audit list.
- **Task 7 — `ship_criteria_check.py`** (commit `45b8d37`, 7 tests). Two-bar gate. Bar 1 (mandatory): 7d rolling hit rate ≥ 62.5% AND Brier ≤ 0.226. Bar 2 (warning): per-p-bucket realized within ±10pp of expected for buckets with ≥ 20 samples (sparse buckets soft-pass). Telegram-style digest renderer + escalation recommendation (`prior_alpha=5` for headline fail, `manual_review_required` for bucket fail). Exit 0 = ship-ready, exit 2 = not ready. Implementer caught a numpy-bool bug in the plan reference and fixed it.

### §22.3 Safety net + docs + activation (Tasks 8–10)

- **Task 8 — 3-of-7 auto-rollback** (commit `3ef8614`, 5 tests). Post-ship circuit breaker. After v0.3 promotes from shadow to live, the validate job watches the rolling 7-day window of daily hit rates. If 3 or more days fall under 50%, the scheduler programmatically flips `data/scheduler_config.yaml` back to `mode: shadow` and Telegrams an auto-rollback alert. `should_auto_rollback`, `_query_daily_hit_rates` (UTC-explicit), `_flip_config_to_shadow` (yaml.safe_dump, loses comments — audit is in git diff).
- **Task 9 — Promotion runbook** (commit `c65e4fa`, no tests). `docs/runbooks/v0.3-promotion.md` — six-step operator checklist for the Day-14 ship event. Pre-flight + refit + ship_criteria + flip + monitor + v1.0 tag criteria + manual rollback section. Implementer verified every script name, flag, exit code, and file path against the actual repo.
- **Task 10 — Wire direction module to per-completeness** (commit `c13ab36`, 10 tests). The activation switch. `detect_calibration_format(path)` returns `'per_completeness' | 'legacy' | 'missing'`. `calibrate_direction` dispatcher in `scoring/direction.py`. `daily_scan.run_daily_scan` pre-loads either format ONCE before the symbol loop, per-symbol code branches on the format constant. Backwards-compatible: today's `calibration_1_5_4.json` (legacy schema) keeps working unchanged.

### §22.4 Phase 1.5 weights gap fix (commit `d54b025`, no tests)

Task 6's `refit_tilt_weights_v03.py` reads `data/tilt_weights_phase_1_5.yaml` for the sign-flip comparison baseline. The file never existed. Materialized from the source of truth (`DEFAULT_REGIME_WEIGHTS + MOMENTUM_FLIP_BY_REGIME` in `scoring/direction.py`). CHOP momentum carries the explicit −0.20 (sign-flip applied) so the v0.3 detector fires correctly when shadow data shows positive CHOP momentum correlation (the original 32.8% live miss hypothesis).

### §22.5 v0.3 summary

11 commits over ~3 hours. Suite **296 → 350 (+54)**, all green. ~600 LOC implementation + ~1100 LOC tests. Day-14 workflow reduced to three commands:

```
python scripts/refit_calibration_v03.py --shadow-weight 3.0
python scripts/refit_tilt_weights_v03.py --shadow-weight 3.0
python scripts/ship_criteria_check.py
# review sign_changes block, manually edit scheduler_config.yaml, restart task
```

Plus the 3-of-7 auto-rollback now armed post-ship as a safety net.

---

## §23 Web UI + cloud migration brainstorm + spec (2026-06-05, commit `23432ca`)

User raised two related problems:

1. The Windows Task Scheduler requires the laptop to be on; if the user is away or the laptop sleeps, no scheduler. Today's session opened with: scheduler died overnight after session ended.
2. Telegram alone is sparse for "watch model + decide" workflows — wanted a web UI.

We brainstormed both together because the UI naturally lives on whatever server hosts the always-on scheduler.

### §23.1 Brainstorm decision provenance

| ID | Question | Choice |
|---|---|---|
| Q1 | UI scope | E — combo (dashboard + track record + operator) |
| Q2 | Live database scope | E — full mart (predictions + prices + intel-hub + manual annotations + portfolio) |
| Q3 | Hosting target | Hetzner CPX11 Falkenstein (€4/month) |
| Q4 | Migration cadence | A — hard cutover + data migrate (zero data loss) |
| Q5 | UI auth model | A — Cloudflare Access (magic link / Google OAuth, one-email allowlist) |
| Q6 | First-ship UI scope | B — MVP 3 screens + iterate, with Ask Claude tab added to v1.0 |
| add | SSH access for the agent | A — full access via `crypto-predictor` deploy user with key auth + sudo restricted to three service restarts |
| add | Domain | `predictor.kry.app` (Cloudflare Registrar, $9/year) |
| add | Deploy workflow | Manual `git pull && systemctl restart`; GitHub Actions deferred |
| add | Secrets management | `/etc/crypto-predictor/secrets.env` + systemd `EnvironmentFile=` |
| add | Backup | Nightly `pg_dump` + parquet rsync to local `/var/lib/crypto-predictor/backups/` |

### §23.2 What got added beyond the original "just a UI" ask

The "Ask Claude" tab. User asked: "from the UI, will I be able to reach you?" Two interpretations:
- The Claude Code agent (this session): NO. My session lives in the Windows terminal; the Hetzner server can't push to it.
- A server-side Claude agent: YES via Anthropic API + Claude Agent SDK. Different agent (no shared memory with this session) but same model family, with tool access to the DB / scripts / journal. Mobile-first.

We added "Ask Claude" as a fourth v1.0 tab. Cost cap via `CLAUDE_DAILY_USD_LIMIT` env var (default $5/day). Session continuity via `claude_chat_log` PG table.

### §23.3 SSH ergonomics test (this session)

Tested before committing to the SSH-access decision:
- `ssh -V` → OpenSSH 10.2 installed ✓
- TCP + TLS handshake to GitHub works (host key added to `~/.ssh/known_hosts`) ✓
- No SSH keys currently exist on this machine (git push uses HTTPS + Windows Credential Manager)
- Bash tool's `~` resolves to `/c/Users/Koray` = PowerShell's `$HOME` ✓ — keys created in either context are mutually visible
- `.ssh/config` write/read works from Bash ✓

Migration day workflow documented: user generates ed25519 keypair in PowerShell, uploads `.pub` to Hetzner panel, accepts host key on first login, appends a `Host crypto-predictor` block to `~/.ssh/config`, then my Bash tool runs any `ssh crypto-predictor "<cmd>"`.

### §23.4 Spec shipped

`docs/superpowers/specs/2026-06-05-web-ui-cloud-migration-design.md`, 540 lines, 10 sections. Commit `23432ca`, pushed.

Sections: architecture, migration sequence (T+0 → T+210, 06:00 UTC avoidance constraint), PG schema (10 migrated tables + 7 new mart tables with type uplift table), Streamlit v1.0 (4 screens with build budget), out of scope (16 items), ops (deploy + secrets + backup + SSH), risk register (15 risks), success criteria + ship blockers, open questions, v0.3 dormant interaction note.

Self-review applied: scheduling-window constraint added (don't span 06:00 UTC during cutover); type uplift rules expanded into a table.

---

## §24 State as of end-of-session (2026-06-05)

### What's live

- Windows Task Scheduler `CryptoPredictorScheduler` running (PID rotates; check `Get-ScheduledTask`)
- Shadow data accumulating in local `predictions.db` (684 rows from June 4; June 5 adds whatever the cron fired today, untouched by us today)
- Telegram heartbeat + post-validation digest go to `kkorkmaz1881@gmail.com`'s bot at 06:00 / 06:30 UTC daily
- v0.3 code shipped + tested but NOT activated; `data/scheduler_config.yaml` still on `mode: shadow, calibration_version: 1_5_4`

### What's queued

1. **User review of the v1.0 spec** (`docs/superpowers/specs/2026-06-05-web-ui-cloud-migration-design.md`) — gate before plan writing
2. **Two implementation plans** (writing-plans skill, when spec is approved):
   - `docs/superpowers/plans/2026-06-05-cutover-runbook.md` — migration day step-by-step
   - `docs/superpowers/plans/2026-06-05-ui-v1.0-build.md` — Streamlit 4 screens, subagent-driven
3. **Day-14 v0.3 ship event** — runs against shadow data accumulated to that point. The migration to Hetzner does NOT reset the 14-day clock; SQLite → PG transfer preserves all shadow rows. Day-14 currently projected: ~2026-06-18 if migration happens this week.

### What lives off-repo (so context fade doesn't lose it)

- `data/secrets.env` — gitignored; contains `TELEGRAM_BOT_TOKEN`, `NEWSAPI_API_KEY` populated; `ANTHROPIC_API_KEY` slot exists but empty (will be filled during UI build for Ask Claude)
- `data/scheduler_config.yaml` — tracked; currently `mode: shadow`
- `data/mcap_ranks.yaml` — tracked; 250 entries from CoinGecko, refresh manually periodically
- `data/tilt_weights_phase_1_5.yaml` — tracked; baseline for v0.3 sign-flip audit
- `~/.crypto-predictor-backups/` — nightly SQLite backups from §19.3
- `logs/scheduler_persistent.log` — append-only; rotate manually if it grows

### Test count progression

| Milestone | Suite size |
|---|---|
| End of 2026-06-03 session | 277 |
| After §21 bug audit + 10 fixes | 296 |
| After §22 v0.3 Tasks 1–10 | 350 |
| After §26 UI Tasks 1–9 | 465 |
| Current | 465 |

---

## §25 Two implementation plans written (2026-06-05, commit `5e32ec1`)

After the v1.0 spec was approved (§23.4), the brainstorming skill mandates the writing-plans skill next. Two plans derived from the spec, both ~500+ lines:

- **`docs/superpowers/plans/2026-06-05-cutover-runbook.md`** — operational runbook the OPERATOR (Koray) executes manually. 34 steps split into pre-cutover prep + 5 phases (A: base server + SSH access, B: code + PostgreSQL, C: systemd services + Cloudflare Tunnel, D: smoke test, E: decommission Windows). Each step tagged `[local]` / `[server]` / `[browser]` / `[via me]` so the operator knows whether to run PowerShell, click a panel, or ask the agent to SSH. Rollback path documented for any step before T+195. 24-hour post-cutover monitoring + backup-restore smoke test scheduled for the first week.

- **`docs/superpowers/plans/2026-06-05-ui-v1.0-build.md`** — subagent-driven implementation plan for the 4-screen Streamlit + intel-bridge build. 10 tasks: migration script, schema bootstrap, UI scaffold, Dashboard page, Track Record page, Operator page + `/jobs` endpoint, Ask Claude (6 tools), systemd units, intel-bridge poller, smoke + v1.0 tag.

Self-review applied: cutover Step 16 cleanup (inline reasoning removed, single coherent root + chown command sequence), UI Task 1 Step 4 clarified (phantom "Task 1.5" reference fixed; PG insert smoke happens during cutover Step 28, not in a separate task).

User approved both plans the same day. Execution started immediately on UI Tasks 1–5, which build against the local Windows machine and don't require Hetzner. Tasks 6–10 partly require Hetzner but were authored ahead of cutover so the post-migration deploy is just `git pull` + `systemctl restart`.

---

## §26 UI v1.0 Tasks 1–9 shipped via subagent-driven-development (2026-06-05)

Same pattern as v0.2.1 and v0.3: one implementer subagent dispatch per task, controller diff-reviews + runs the test slice + commits, continuous execution. 9 of 10 tasks shipped in a single session. Task 10 (smoke + v1.0 tag) requires a real Hetzner deploy and is deferred to post-cutover.

### §26.1 Foundation (Tasks 1–3, commits `95b1220`, `9ed325c`, `f9de9aa`)

- **Task 1 — `scripts/migrate_sqlite_to_postgres.py`** (commit `95b1220`, +15 tests). Reads the three SQLite DBs and ports them to PG with idempotent `ON CONFLICT DO NOTHING`. Implementer caught five improvements vs the reference skeleton, the most important being **reserved-word handling**: `metrics_rolling.window` is a PG reserved word, requires double-quote escaping; without it the real cutover INSERT would have crashed on the first metrics row. Live dry-run against the local DBs reported 23,078 total rows across 10 tables. `psycopg[binary]>=3.2` added as a dep, lazy-imported so `--dry-run` doesn't require it.

- **Task 2 — PG schema bootstrap** (commit `9ed325c`, +15 tests). `migrations/001_initial_schema.sql` (316 lines) — all 17 production tables + the `_migrations` tracker. `scripts/init_postgres_schema.py` applies migrations in lexical order, tracks SHA-256 per file, logs `init_sha_drift` warning when a previously-applied file's hash changes. Idempotent: every CREATE TABLE / CREATE INDEX uses `IF NOT EXISTS`. CHECK constraints on enum-like columns (mode, status, regime, confidence_flag, feature_completeness). FK `predictions_features → predictions ON DELETE CASCADE`; `manual_annotations → predictions ON DELETE SET NULL`. GIN index on `news_feed.symbols_mentioned` array; partial index `WHERE closed_at IS NULL` on `manual_annotations`. The `_migrations` tracker is declared first in the file.

- **Task 3 — UI scaffold** (commit `f9de9aa`, +7 tests). `src/crypto_predictor/ui/` package with `app.py` (entry point using `st.navigation`), `db.py` (`@st.cache_resource` `ConnectionPool` size 2..5), `auth.py` (Cloudflare Access header reader with dev fallback). Four page placeholder modules under `pages/`. `streamlit>=1.40` + `psycopg-pool>=3.2` added to deps. The `st.context.headers` API requires Streamlit 1.40+, documented in `auth.py`.

### §26.2 Three pages (Tasks 4–6, commits `90a9e59`, `a06402a`, `da9b386`)

- **Task 4 — Dashboard page** (commit `90a9e59`, +8 tests). `src/crypto_predictor/ui/queries.py` ships `todays_slate(conn, mode)` returning regime, calibration version, mode, n_predictions, n_wild_cards, n_ceiling_hit, top_long, top_short, wild_cards, active_annotations, next_scan_dt. Page renders metric strip + three sortable dataframes + annotations placeholder. Composite scores displayed as basis points (consistency with markdown report from §19.9). 60-second cache TTL. Implementer added Decimal→float coercion in `_rows_to_dicts` so PG `NUMERIC` returns don't break Streamlit/pandas; added `(confidence_flag IS NULL OR <> 'WILD_CARD')` to keep NORMAL+NULL-flag rows in long/short tables.

- **Task 5 — Track Record page** (commit `a06402a`, +9 tests). Four new query helpers in `queries.py`: `rolling_kpis`, `per_bucket_calibration`, `daily_hit_rates`, `by_regime_and_flag`. Page renders five-metric KPI strip with delta vs 62.5%/0.226 baselines, plotly line chart for daily hit rate trend with 62.5% baseline ribbon, plotly scatter for per-p-bucket calibration (size+color by sample count, y=x diagonal overlay), regime × flag breakdown table, and a "Run ship_criteria_check.py" button that subprocesses the script and gates on exit code 0/2/other. 5-minute cache TTL. Critical for the v0.3 dormant-window operator: this is the screen that tells the user when shadow data is ripe for the Day-14 ship.

- **Task 6 — Operator page + `/jobs` HTTP endpoint** (commit `da9b386`, +16 tests). `scripts/run_scheduler.py` extended with `_build_jobs_app(scheduler)` factored out for testability (Flask test client; no live port bind in unit tests) and `_start_jobs_endpoint` that spawns a daemon thread on `127.0.0.1:8502` ONLY on the production path (skipped when `stop_event` injected by tests). `src/crypto_predictor/ui/systemd_helpers.py` exposes `systemd_available`, `scheduler_status`, `next_jobs`, `restart_service`, `tail_journal`, `trigger_script` — every helper degrades gracefully on Windows where `systemctl` is absent. Page implements six sections per spec §4.3 with `type RESTART to confirm` token gate on destructive actions and `EnvironmentFile` preservation on config saves. `flask>=3.0` added as a dep.

### §26.3 Ask Claude (Task 7, commit `cc9b185`)

Biggest single task of the build (~2 days estimated). 30 new tests.

`src/crypto_predictor/ui/claude_tools.py` ships six tools:
- `query_predictions(conn, filters, limit)` with allowlist of filter columns (defends against SQL injection)
- `query_completeness_breakdown(conn, window_days)`
- `query_calibration_state(version)` detecting three on-disk shapes (`legacy`, `per_completeness`, `unknown`) — future-proofs v0.3 → v0.4 schema flip
- `run_ship_criteria_check()` subprocesses the script + regex-parses stdout
- `query_intel_hub(conn, category, hours_back)` merging `whale_txs` + `news_feed` with `source` marker
- `read_journal(section_regex, journal_path)` walks markdown sections with output capped at 8 KB to bound model context

`TOOL_SCHEMAS` module constant holds Anthropic-API-shaped JSON schemas for all six. `dispatch_tool` wrapper splits "needs `conn`" vs not via `TOOLS_NEEDING_CONN`.

`src/crypto_predictor/ui/claude_session.py`:
- `get_or_create_session_id()` — `st.session_state['claude_session_id']` (tab-lifetime, Streamlit has no cookie API)
- `todays_claude_cost(conn)` and `is_cost_capped()` — env var `CLAUDE_DAILY_USD_LIMIT` default $5/day, malformed env falls back to default
- `load_conversation` / `persist_turn` with JSONB tool_calls serialization
- `call_claude(messages, system, tools)` — bare `anthropic` SDK (no `claude-agent-sdk` to avoid asyncio/Streamlit conflicts). Manual tool-use loop with `max_turns=8` safeguard. Prompt caching `cache_control={"type": "ephemeral"}` on the system prompt. Cost computed as `tokens_in * 15e-6 + tokens_out * 75e-6` (claude-opus-4-7 approximate pricing — over-estimation is fine since this is a safety cap, not a billing line).

Page implementation: require_auth → `ANTHROPIC_API_KEY` presence check (warning banner + stop if missing) → cost-cap gate (`is_cost_capped()` before rendering chat input) → session id → history load + render → sidebar cost meter → `st.chat_input` → persist user turn → spinner-wrapped `call_claude` → render assistant + persist with cost. `anthropic>=0.40` added as a dep.

Test coverage proves the cost cap: five tests cover the under/over/default-env/invalid-env paths plus an exact cost-formula assertion (`100 * 15e-6 + 10 * 75e-6 = $0.00225`).

### §26.4 Deploy artifacts (Tasks 8–9, commits `1a9de46`, `bea6ef2`)

- **Task 8 — systemd unit templates + install script** (commit `1a9de46`, +6 tests). Three `.service` files (scheduler, ui, intel-bridge) committed under `deploy/systemd/` with LF line endings, plus `deploy/install_systemd_units.sh` (bash, set -euo pipefail, sudo gate, idempotent enable+start), plus `deploy/README.md` documenting the layout and the post-cutover update flow. `chmod +x` set on the install script via `git update-index --chmod=+x`. UI unit `After=` includes the scheduler so `/jobs` endpoint is up when UI polling starts.

- **Task 9 — intel-bridge poller** (commit `bea6ef2`, +9 tests). `src/crypto_predictor/intel_bridge/` package with `fetchers.py` (Protocol interface + `StubWhaleFetcher` / `StubNewsFetcher` returning `[]`; real fetchers swap in for Day-14 as a one-file change) and `poller.py` (`poll_whales` with `ON CONFLICT (chain, tx_hash) DO NOTHING`; `poll_news` with in-batch dedup on `(source, url, ts)`). `scripts/run_intel_bridge.py` is the systemd entry point with SIGINT/SIGTERM handling, lazy `psycopg.connect`, `INTEL_BRIDGE_INTERVAL_SECONDS` env override defaulting to 900 s, and `max_ticks` parameter that bounds the loop for tests.

### §26.5 Test count progression

| Milestone | Suite size | Δ |
|---|---|---|
| End of §22 (v0.3 done) | 350 | — |
| Task 1: SQLite→PG migrator | 365 | +15 |
| Task 2: PG schema bootstrap | 380 | +15 |
| Task 3: UI scaffold | 387 | +7 |
| Task 4: Dashboard page | 395 | +8 |
| Task 5: Track Record page | 404 | +9 |
| Task 6: Operator + /jobs | 420 | +16 |
| Task 7: Ask Claude | 450 | +30 |
| Task 8: systemd units | 456 | +6 |
| Task 9: intel-bridge | 465 | +9 |
| **Total v1.0 contribution** | **465** | **+115** |

### §26.6 Task 10 deferred to post-cutover

Smoke test against the real Hetzner deployment + polish + `v1.0` git tag requires the cloud server to exist. Task 10 will land in the same session as the cutover or immediately after (per cutover Phase D Step 29).

---

## §27 GitHub push auth fix (2026-06-05)

After Task 6 (commit `da9b386`) `git push` started returning 403 "Permission to kry23/crypto-prediction-hub.git denied to **kry2323**." The first ~5 UI task commits had pushed cleanly. Mid-session something flipped the cached credential to a different GitHub account.

Investigation via PowerShell `cmdkey /list | Select-String github`:
- `LegacyGeneric:target=git:https://github.com` (Git Credential Manager generic)
- `LegacyGeneric:target=gh:github.com:` (gh CLI generic)
- `LegacyGeneric:target=gh:github.com:kry2323` (the wrong-user CLI entry)

`git config --get remote.origin.url` returned `https://github.com/kry23/...` (correct). The 403 was Git Credential Manager finding the `kry2323` token in the cache, sending it, GitHub rejecting because that user doesn't have write access to the `kry23` repo.

**Fix applied**:
1. `cmdkey /delete:LegacyGeneric:target=git:https://github.com` — cleared GCM generic entry
2. `cmdkey /delete:LegacyGeneric:target=gh:github.com:` — cleared gh CLI generic
3. `cmdkey /delete:LegacyGeneric:target=gh:github.com:kry2323` — cleared the wrong-user gh entry
4. `git config --global credential.https://github.com.gitHubAuthModes device` — force device-code flow next time so the agent's non-interactive Bash doesn't hang waiting for a browser

First `git push` after step 3 hung (15s timeout) — Git Credential Manager had opened a browser on the user's machine for OAuth. The user authenticated with the correct `kry23` account in the background. The retry push succeeded immediately because the credentials were now cached correctly. Range pushed: `a06402a..bea6ef2` — UI Tasks 6, 7, 8, 9 + everything since the last successful push.

Aftermath:
- `git config --global --list | grep github` shows the device-flow override is in place. If the cache ever clears again, the next push prints a URL + 8-character code to the terminal instead of opening a browser — works in any shell, including the agent's non-interactive one.
- The wrong-user `kry2323` entries are gone from Credential Manager. Only the correct `kry23` token remains.

This is the kind of operational paper-cut that's worth journaling because it'll likely recur if the user logs into another GitHub account on the same Windows profile.

---

## §28 State as of end-of-session (2026-06-05, post-§26 + post-§27)

### What's live

- Windows Task Scheduler `CryptoPredictorScheduler` running (or stopped between sessions; check `Get-ScheduledTask`); shadow data accumulating in local `predictions.db`
- Telegram heartbeat + post-validation digest go to the user's bot at 06:00 / 06:30 UTC daily IF the scheduler is alive
- v0.3 code (commits `ced7a04` … `c13ab36`) + UI v1.0 code (`95b1220` … `bea6ef2`) all shipped + pushed to origin
- 465 tests, all green
- `data/scheduler_config.yaml` still on `mode: shadow, calibration_version: 1_5_4` (v0.3 not promoted yet)

### What's queued

1. **GitHub push auth — fixed** (§27). No user action needed.
2. **Cutover day scheduling** — user decides; constraint is the migration window must NOT span 06:00 UTC (cutover stops the Windows scheduler at T+0, so an in-window 06:00 UTC firing is lost)
3. **UI Task 10** — smoke + polish + `v1.0` git tag, ~1–2 hours work on the Hetzner box, runs as part of the cutover Phase D or immediately after
4. **Day-14 v0.3 ship** — `python scripts/refit_calibration_v03.py && python scripts/refit_tilt_weights_v03.py && python scripts/ship_criteria_check.py`, then edit `data/scheduler_config.yaml`. Currently projected for ~2026-06-18 if migration happens before then; migration preserves shadow data so the 14-day clock keeps ticking through it.

### What lives off-repo (so context fade doesn't lose it)

Same as §24, plus:
- `~/.gitconfig` global now has `credential.https://github.com.gitHubAuthModes=device` from §27 fix
- Windows Credential Manager has only the **correct** `kry23` GitHub PAT cached (after §27); previous `kry2323` entries deleted
- `pyproject.toml` dependencies grew during §26: `streamlit>=1.40`, `psycopg[binary]>=3.2`, `psycopg-pool>=3.2`, `flask>=3.0`, `anthropic>=0.40` — five new lines

### Active CLAUDE-side decisions waiting on the user

- **Cutover day** — pick a window away from 06:00 UTC. Recommended: a Saturday or Sunday afternoon TR time (12:00 UTC = 15:00 TR is a clean choice). Until then, the Windows scheduler is the operational scheduler.

(The previous "spec review verdict" and "plan review verdict" decisions from §24 are both now resolved — user approved both.)

### Session arc

This is the third consecutive day of substantial work:
- **2026-06-03**: v0.2.1 shadow infrastructure ship + spec/plan brainstorming for v0.3
- **2026-06-04**: bug audit + 10 fixes + persistent operation
- **2026-06-05**: v0.3 implementation Tasks 1–10 + web UI brainstorm + spec + 2 plans + UI Tasks 1–9 + push auth fix

The crypto-predictor codebase grew from a single-file SQLite + Telegram-only system on 2026-06-03 to a full Streamlit web app + PG-backed mart + cloud-deployable architecture by end of 2026-06-05, with v0.3 calibration revision ready to ship on Day-14 and all v1.0 UI build code shipped (and largely tested) ahead of the actual cloud cutover.

The dormant phase begins now in earnest.

---

## §29 Cloud cutover executed (2026-06-05/06, commit `29a7697`)

The cutover from the spec/plan (§23, §25) was executed live. It deviated from the runbook in four material ways, each forced by reality:

### §29.1 Provider: Hetzner → Hostinger
DigitalOcean and Hetzner both failed at payment/verification (recurring TR-card friction). Landed on a **Hostinger KVM VPS** (Ubuntu 24.04, 2 vCPU / 4 GB / ~48 GB, Germany). The runbook is 95% provider-agnostic — only the ordering screen changed; everything from `ssh root@` onward (Step 7+) ran verbatim. The SSH keypair (`~/.ssh/hetzner_key`, kept the name) + `~/.ssh/config` alias `crypto-predictor` worked unchanged.

Server: `109.106.244.78`. Deploy user + restricted sudo (`/usr/bin/systemctl` — the runbook's `/bin/systemctl` would NOT have matched sudoers on 24.04). PG 16 tuned to detected RAM (shared_buffers 979 MB). PG password generated **server-side** and written straight into `secrets.env` — never entered the agent's context.

### §29.2 Secrets architecture fix (not in the runbook)
The code reads `load_secrets(project_root/"data"/"secrets.env")` — a **file**, not env vars. The runbook put secrets in `/etc/crypto-predictor/secrets.env` for systemd `EnvironmentFile=`. Two different mechanisms. Resolved with a **symlink**: `data/secrets.env → /etc/crypto-predictor/secrets.env`, so `load_secrets()` (file read via symlink) and systemd (`EnvironmentFile=` direct) share one source. The local `data/secrets.env` actually had `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` + `NEWSAPI_API_KEY` (a PowerShell regex/BOM quirk had hidden two of them in an earlier check); merged server-side without exposing values.

### §29.3 DNS: GoDaddy → Cloudflare, and auth: Zero Trust → nginx basic-auth
`krypredictor.com` was registered at GoDaddy (NS `domaincontrol.com`), not on Cloudflare. Added the zone to Cloudflare, switched nameservers at GoDaddy (`memphis`/`mimi.ns.cloudflare.com`) — propagated in minutes. Deleted the imported GoDaddy parking A records.

Cloudflare Tunnel: the connector was first mistakenly installed on **Windows** (`cloudflared.exe`); reinstalled on the server (token-managed, 4 QUIC conns to ams). The new "Networking → Tunnels" UI hid the public-hostname step, so the ingress (`krypredictor.com → http://localhost:80`) + the apex DNS CNAME (`→ <tunnel>.cfargotunnel.com`, proxied) were set **via the Cloudflare API** (after the user supplied a scoped token; needed two tries — first token lacked Account:Cloudflare Tunnel:Edit).

**Cloudflare Access (Zero Trust) requires a billable payment method** the user couldn't add. Pivoted the auth model entirely: **nginx basic-auth** on the box in front of Streamlit. Chain: `browser → Cloudflare TLS → tunnel → nginx:80 (htpasswd) → streamlit:8501`. Zero cost, no Zero Trust. (Login: user `koray`, password generated server-side.) This supersedes the spec's Q5 = Cloudflare Access decision. The UI's `auth.py` Cloudflare-Access header reader falls back to dev-mode (single user), which is fine behind the nginx gate.

### §29.4 Split-brain discovered + sync bridge (commit `29a7697`)
Phase-D smoke scan ran clean (343 predictions, Telegram + report) but **PG row count didn't move**. Root cause: the entire prediction pipeline (`storage/predictions_db.py`, and validate/recalibrate/metrics in `jobs.py`) writes/reads **SQLite**; only the UI reads **PG**. The UI-build migration (§26 Task 1) was a one-time port + UI-side PG reads; the **writer was never converted**. Spec §10 had flagged the scripts as SQLite-needing-PG-changes, so this was a known-deferred gap that the cutover hit head-on.

Surfaced the full scope to the user: **48 files** touch SQLite (~12 core src, ~15 scripts, ~20 tests that build tmp `.db` fixtures and would need a local PG test harness). A full PG conversion is a v1.1 project, not a cutover step. User chose the **bridge**: `scripts/sync_sqlite_to_pg.py` mirrors SQLite→PG on a systemd timer every 10 min. Crucially it **UPSERTs** (the one-time migrator is insert-only), so a validated prediction's `status` flip propagates — verified live with a reversible `pending→expired→pending` round-trip. `predictions_features` stays insert-only (immutable, append-only). 6 unit tests for the conflict-clause builder; suite **471**.

### §29.5 End state
- All 4 services `active`, 0 restarts: scheduler (6 cron jobs, UTC), ui (127.0.0.1:8501), intel-bridge, cloudflared. Sync timer armed (next :00/:10/…).
- `https://krypredictor.com` live: no-auth → 401, auth → 200 (Streamlit). PG 1382 predictions (343 today). Mem 848/3916 MB, disk 9%.
- Windows Task Scheduler **disabled (not yet uninstalled)** — kept as a one-command rollback fallback until the server fires its first full 06:00 UTC cycle (2026-06-06). Final decommission (cutover Phase E Steps 31–32) deferred to after that proves out.
- Data flow end-to-end: scheduler writes SQLite → sync timer (≤10 min) → PG → UI. Daily 06:00 predict + 06:30 validate both propagate to the UI automatically.

### §29.6 Open follow-ups
1. **Confirm tomorrow's 06:00 UTC server cycle** fires (Telegram heartbeat from the box), then uninstall the Windows task (Phase E).
2. **v1.1 — convert pipeline to PG-native** (retire the bridge). Proper brainstorm + plan + TDD; needs a PG test harness (pytest-postgresql / testcontainers) for the ~20 SQLite-fixture tests.
3. UI Task 10 (smoke + `v1.0` tag) — partially satisfied by this live deploy; formal tag pending the PG-native milestone or a conscious decision to tag v1.0 with the bridge in place.
4. Day-14 v0.3 ship still tracks against shadow rows (684 + daily), now accumulating reliably on the always-on box.

---

*End of session journal. 2026-06-04 + 2026-06-05 + 2026-06-06 cutover.*
