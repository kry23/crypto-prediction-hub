# Web UI + Cloud Migration — Design Spec

**Date**: 2026-06-05
**Status**: Brainstorming complete, awaiting user spec review
**Trigger**: Windows Task Scheduler lives only while the user's laptop is on; persistent operation needs a server. While migrating to a cloud host, fold in a web UI for "watch model + decide" workflows that today happen via Telegram + ad-hoc terminal access.

## Goal

Stand up an always-on Hetzner VPS running the scheduler under systemd, migrate the SQLite + parquet data store into PostgreSQL 16, expose a Streamlit web UI behind Cloudflare Access (magic-link auth) with four screens (Dashboard, Track Record, Operator, Ask Claude), and decommission the Windows Task Scheduler in a single ~3.5-hour cutover. Zero data loss; v0.3 dormant timeline continues uninterrupted.

## Brainstorm decisions (provenance)

| ID | Decision | Choice | Section |
|---|---|---|---|
| Q1 | UI scope | E — combo (dashboard + track record + operator) | §4 |
| Q2 | Live database scope | E — full mart (predictions + prices + intel-hub + manual annotations + portfolio) | §3 |
| Q3 | Hosting target | Hetzner CPX11 Falkenstein, €4/month | §1 |
| Q4 | Migration cadence | A — hard cutover + data migrate (zero data loss) | §2 |
| Q5 | UI auth model | A — Cloudflare Access (magic link / Google OAuth, 50 free users) | §1 |
| Q6 | First-ship UI scope | B — MVP 3 screens + iterate, with Ask Claude tab added to v1.0 | §4 |
| add | SSH access for the agent | A — full access via `crypto-predictor` deploy user with key auth | §6 |
| add | Domain | `predictor.kry.app` (Cloudflare Registrar, $9/year) | §1 |
| add | Deploy workflow | Manual `git pull && systemctl restart`; GitHub Actions deferred | §6 |
| add | Secrets management | `/etc/crypto-predictor/secrets.env` (root:crypto-predictor 640, systemd `EnvironmentFile=`) | §6 |
| add | Backup | Nightly `pg_dump` + parquet rsync to local `/var/lib/crypto-predictor/backups/` | §6 |

---

## §1 — Architecture overview

```
┌────────────────────────────────────────────────────────────┐
│  Cloudflare Tunnel + Access (magic link)                   │
│  https://predictor.kry.app  → tunnel → server:8501         │
└─────────────────────────┬──────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────┐
│  Hetzner CPX11 Falkenstein (Ubuntu 24.04, 4GB RAM, 40GB)   │
│                                                            │
│  /opt/crypto-predictor/        ← git clone                 │
│  /opt/crypto-predictor/venv/                               │
│  /var/lib/postgresql/16/                                   │
│  /var/lib/crypto-predictor/                                │
│    ├── history/  (parquet OHLCV mirror, scp'd from Win)    │
│    ├── backups/  (nightly pg_dump + parquet snapshot)      │
│    └── logs/     (systemd journal mirror, optional)        │
│  /etc/crypto-predictor/                                    │
│    └── secrets.env  (root:crypto-predictor 640, gitignored)│
│                                                            │
│  ─ systemd services ─                                       │
│  crypto-predictor-scheduler.service     (APScheduler)      │
│  crypto-predictor-ui.service            (Streamlit :8501)  │
│  crypto-predictor-intel-bridge.service  (intel-hub poller) │
│  postgresql.service                                        │
│  cloudflared.service                    (Tunnel daemon)    │
│                                                            │
│  ─ deferred / optional ─                                    │
│  crypto-predictor-prices.service  (WebSocket OKX, v1.3)    │
└────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   OKX API           NewsAPI         CoinGecko + Telegram
   (ccxt)            (sentiment)     (global + bot)
```

### Component decisions

- **Host**: Hetzner CPX11 (€4/mo, 2 vCPU, 4 GB RAM, 40 GB SSD, EU). Falkenstein location for low Turkey ping.
- **OS**: Ubuntu 24.04 LTS. Standard apt packaging avoids vendor lock-in.
- **DB**: PostgreSQL 16 (Ubuntu default via apt). No managed-DB upcharge.
- **Scheduler**: existing APScheduler code wrapped in a systemd unit; no logic change.
- **UI tech**: Streamlit for v1.0 (Python-native, fast to build, sufficient for 4 screens). React+FastAPI port is deferred to v2.0 if Streamlit hits performance or layout limits.
- **AI assistant**: server-side Anthropic API + Claude Agent SDK with tools (DB query, script run, journal read).
- **Auth**: Cloudflare Access magic link. User's email on a one-entry allowlist. 24-hour session cookie.
- **TLS**: Cloudflare Tunnel (no certbot needed; Cloudflare manages certs end-to-end).
- **Domain**: `predictor.kry.app`. Apex `kry.app` registered fresh via Cloudflare Registrar (~$9/year). Other subdomains free for future projects.

---

## §2 — Migration sequence (cutover day)

Estimated total: ~3.5 hours. Roll-back plan: re-enable the Windows Task Scheduler (`pwsh install_windows_scheduler.ps1`). Windows-side data is untouched until the final step, so zero-loss rollback any time before T+195.

**Scheduling constraint**: pick a window that does NOT span 06:00 UTC. The cutover stops the Windows scheduler at T+0; if the 06:00 UTC cron is inside the window, that day's cohort is lost. Recommended: start cutover ≥ 4 hours after 06:00 UTC (e.g., 12:00 UTC start = 15:30 UTC finish on the same day, well clear of the next 06:00 UTC firing).

```
T+0    Hetzner CPX11 order (card on file), SSH key upload, base Ubuntu 24.04 (15 min)
T+15   Cloudflare account (or existing), DNS A record for predictor.kry.app,
       cloudflared tunnel created in panel (10 min)
T+25   apt install: python3.12, python3.12-venv, postgresql-16, postgresql-client-16,
       nginx, git, cloudflared (5 min)
T+30   useradd crypto-predictor, /opt/crypto-predictor git clone, venv create,
       pip install -e ".[dev]" (15 min)
T+45   PostgreSQL init: createuser, createdb, scripts/migrate_sqlite_to_postgres.py
       end-to-end (predictions.db + sentiment_cache.db + global_cache.db → PG) (30 min)
T+75   scp from Windows: data/history/*.parquet (~3 GB),
       calibration_*.json, sector_map.yaml, scheduler_config.yaml,
       equity_blacklist.yaml, mcap_ranks.yaml, tilt_weights_*.yaml,
       and predictions DB JUST-IN-CASE if first migration missed rows (~30 min)
T+105  systemd unit installation: scheduler + UI + intel-bridge units in
       /etc/systemd/system/, daemon-reload, enable, start.
       cloudflared service connects to tunnel; Cloudflare Access policy:
       email allowlist with kkorkmaz1881@gmail.com (45 min)
T+150  Smoke test:
       - python scripts/predict_scan_cli.py → completes end-to-end
       - shadow scan row count matches Windows DB pre-migration
       - Telegram heartbeat lands
       - UI loads with all 4 tabs at https://predictor.kry.app (45 min)
T+195  Windows-side: pwsh -File scripts\uninstall_windows_scheduler.ps1
       Telegram: "🚀 Migrated to predictor.kry.app" announcement (15 min)
T+210  Done. ~3.5 h elapsed.
```

**Pre-cutover-day prep (the day before, ~30 min)**: Order Hetzner ahead of time so provisioning is done; generate SSH keypair; have public key ready to paste into Hetzner panel.

---

## §3 — PostgreSQL schema design

### Migrated tables (1:1 from SQLite, no schema changes beyond type uplifts)

```sql
-- predictions.db carries forward
CREATE TABLE predictions (...);            -- includes v0.2.1 mode/feature_completeness columns
CREATE TABLE predictions_features (...);
CREATE TABLE calibration_maps (...);
CREATE TABLE regime_log (...);
CREATE TABLE metrics_rolling (...);
CREATE TABLE patterns (...);
CREATE TABLE runs (...);

-- sentiment_cache.db
CREATE TABLE sentiment_cache (...);

-- global_cache.db
CREATE TABLE global_cache (...);
CREATE TABLE coin_btc_corr (...);
```

### Type uplift rules (SQLite TEXT → PG)

| SQLite column type | PG target | Examples |
|---|---|---|
| ISO 8601 TEXT timestamps | `TIMESTAMPTZ` | `created_at`, `validated_at`, `asof`, `timestamp` |
| Price-like REAL | `NUMERIC(20, 8)` | `target_value`, `actual_outcome` (fractional returns), OHLCV |
| Probability REAL | `NUMERIC(10, 8)` | `p_direction`, `composite_score`, `brier` |
| Integer counts | `INTEGER` or `BIGINT` | `horizon_hours`, `n_predictions` |
| Enum-like TEXT (status, mode, regime, confidence_flag, feature_completeness) | `VARCHAR(20)` + CHECK constraint | — |
| Free-text TEXT | `TEXT` | `evaluation`, `missing_features` (comma-list), `error_summary` |

Index parity: every SQLite index recreated on the PG side, plus the v0.2.1 indexes on `mode` and `feature_completeness` and the new GIN/partial indexes in §3 above.

### New tables (live mart, E scope from Q2)

```sql
-- A) Live OKX prices (deferred to v1.3 enable; schema present at v1.0 ship)
CREATE TABLE prices_1m (
    symbol           VARCHAR(40) NOT NULL,
    ts               TIMESTAMPTZ NOT NULL,
    open             NUMERIC(20, 8),
    high             NUMERIC(20, 8),
    low              NUMERIC(20, 8),
    close            NUMERIC(20, 8),
    volume_quote     NUMERIC(24, 4),
    PRIMARY KEY (symbol, ts)
);
CREATE INDEX idx_prices_1m_ts ON prices_1m(ts DESC);

-- B) Whale TXs from crypto-intel-hub MCP bridge (v1.0 populated)
CREATE TABLE whale_txs (
    id               BIGSERIAL PRIMARY KEY,
    chain            VARCHAR(20) NOT NULL,
    symbol           VARCHAR(40),
    tx_hash          VARCHAR(80) NOT NULL,
    amount_usd       NUMERIC(20, 2),
    from_label       VARCHAR(120),
    to_label         VARCHAR(120),
    ts               TIMESTAMPTZ NOT NULL,
    raw_json         JSONB NOT NULL,
    UNIQUE (chain, tx_hash)
);
CREATE INDEX idx_whale_txs_ts ON whale_txs(ts DESC);

-- C) News feed from crypto-intel-hub
CREATE TABLE news_feed (
    id                BIGSERIAL PRIMARY KEY,
    category          VARCHAR(20) NOT NULL,
    severity          VARCHAR(10) NOT NULL,
    title             TEXT NOT NULL,
    url               TEXT,
    source            VARCHAR(40),
    symbols_mentioned TEXT[],
    sentiment         NUMERIC(4, 3),
    ts                TIMESTAMPTZ NOT NULL,
    raw_json          JSONB NOT NULL
);
CREATE INDEX idx_news_feed_ts ON news_feed(ts DESC);
CREATE INDEX idx_news_feed_category ON news_feed(category);
CREATE INDEX idx_news_feed_symbols ON news_feed USING GIN (symbols_mentioned);

-- D) Manual annotations (schema present at v1.0; form ships v1.2)
CREATE TABLE manual_annotations (
    id                BIGSERIAL PRIMARY KEY,
    prediction_id     VARCHAR(40) REFERENCES predictions(id) ON DELETE SET NULL,
    symbol            VARCHAR(40),
    note              TEXT NOT NULL,
    action_taken      VARCHAR(20),
    entry_price       NUMERIC(20, 8),
    target_price      NUMERIC(20, 8),
    stop_price        NUMERIC(20, 8),
    position_size_usd NUMERIC(20, 2),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at         TIMESTAMPTZ,
    realized_pnl_usd  NUMERIC(20, 2)
);
CREATE INDEX idx_manual_annotations_symbol ON manual_annotations(symbol);
CREATE INDEX idx_manual_annotations_open ON manual_annotations(closed_at)
  WHERE closed_at IS NULL;

-- E) Portfolio holdings (schema present at v1.0; form ships v1.2)
CREATE TABLE portfolio_holdings (
    id            BIGSERIAL PRIMARY KEY,
    asset         VARCHAR(40) NOT NULL,
    quantity      NUMERIC(24, 8) NOT NULL,
    avg_cost_usd  NUMERIC(20, 2),
    venue         VARCHAR(40),
    notes         TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_portfolio_asset ON portfolio_holdings(asset);

-- F) Exchange balance snapshots (schema present at v1.0; poller ships v1.2)
CREATE TABLE exchange_balances (
    id           BIGSERIAL PRIMARY KEY,
    exchange     VARCHAR(40) NOT NULL,
    asset        VARCHAR(40) NOT NULL,
    free         NUMERIC(24, 8),
    used         NUMERIC(24, 8),
    total        NUMERIC(24, 8),
    snapshot_ts  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_exchange_balances_ts
  ON exchange_balances(exchange, asset, snapshot_ts DESC);

-- G) Ask Claude chat log (v1.0)
CREATE TABLE claude_chat_log (
    id          BIGSERIAL PRIMARY KEY,
    session_id  UUID NOT NULL,
    role        VARCHAR(20) NOT NULL,
    content     TEXT NOT NULL,
    tool_calls  JSONB,
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    cost_usd    NUMERIC(8, 4),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_claude_chat_log_session ON claude_chat_log(session_id, created_at);
```

### Schema rationale (short)

- **`TIMESTAMPTZ` everywhere** — PG's native UTC handling ends the `datetime('now', 'utc', ...)` SQLite gymnastics.
- **`JSONB` for raw responses** — intel-hub MCP, NewsAPI, whale-watch all produce different schemas; flexible storage avoids ETL pain.
- **GIN index on `symbols_mentioned[]`** — fast "all BTC news in last 24h" queries.
- **Partial index `WHERE closed_at IS NULL`** — only indexes open annotations, tiny + fast.
- **`NUMERIC(20, 8)` for prices** — 1 satoshi precision; `DOUBLE PRECISION` floats avoided to prevent rounding error in PnL math.
- **`BIGSERIAL` for new tables** — 2³² (4 billion) row ceiling on SERIAL is enough today but cheap to future-proof.

### Migration script

`scripts/migrate_sqlite_to_postgres.py`:
- Inputs: paths to all 3 SQLite DBs + PG connection string
- Per-table: `SELECT *` from SQLite → batched `INSERT … ON CONFLICT DO NOTHING` into PG
- Idempotent (re-run safe; conflicts skip)
- Progress bar (`tqdm`) per table
- Estimated runtime: ~5 minutes for the current data (a few thousand rows total + 30 sentiment cache rows + 1 global cache row)
- Self-checks: row count parity report at the end

### PG tuning

- `shared_buffers = 1GB` (~25% of 4 GB RAM)
- `effective_cache_size = 2GB`
- `max_connections = 50` (well above expected ~10 concurrent: UI + scheduler + intel-bridge + bridge background)
- `work_mem = 16MB` (per-query sort, OK for this dataset)
- `wal_level = replica` (default; no streaming replication on single-node)
- WAL archiving OFF (single-node, backup is `pg_dump`-based)

### Auth

- Unix-socket: `peer` auth for the `crypto-predictor` OS user → no password needed by services on the same box
- Network: `password` auth on localhost only (`host crypto_predictor crypto_predictor 127.0.0.1/32 scram-sha-256`), used by Streamlit and Anthropic Agent SDK tools
- Connection string in `/etc/crypto-predictor/secrets.env`: `DATABASE_URL=postgresql://crypto_predictor:****@127.0.0.1:5432/crypto_predictor`

---

## §4 — Streamlit v1.0 (4 screens)

### 4.0 Shell

- `st.navigation` with 4 pages: Dashboard, Track Record, Operator, Ask Claude
- Header strip: project name + current `mode` badge + Cloudflare Access user email
- Global `st.session_state.user_email` from Cloudflare Access `CF-Access-Authenticated-User-Email` header
- Auto-refresh: per-page TTL (Dashboard 60 s, Track Record 5 min, Operator 10 s, Ask Claude on-demand)
- PG connection pool: `psycopg_pool.ConnectionPool` size 5, single global instance via `@st.cache_resource`
- Build: 1 day (the shell ALSO does global auth check, error boundaries, etc.)

### 4.1 Dashboard

**Goal**: "What is today's slate and why?"

Layout: header card → top long table → top short table → wild cards table → active annotations (v1.2 placeholder).

Data sources: `predictions` (mode='shadow' AND `created_at > today`), `regime_log` (today's regime), `calibration_maps` (active version), `manual_annotations` (open positions).

Streamlit components: `st.metric`, `st.dataframe` (sortable, selectable), `st.expander`, `plotly` mini-sparkline for "next scan countdown".

Click-through: clicking a row navigates to Per-Prediction Drill-Down (v1.1; v1.0 shows a `st.toast` "coming in v1.1").

Build: 2 days.

### 4.2 Track Record

**Goal**: "How well is the model actually doing, is calibration healthy, is v0.3 ready to ship?"

Layout:
- Top row: window selector (7d / 30d / 90d / all-time) + mode selector (shadow / live / all)
- KPI strip: hit rate vs baseline, Brier vs baseline, closed / pending / expired counts
- Hit rate trend line chart with horizontal baseline ribbon at 62.5%
- Calibration scatter: predicted vs realized, one dot per p-bucket, color by sample size, y=x diagonal overlay
- Breakdown table: regime × confidence_flag × n × hit rate
- "Run ship_criteria_check.py" button → output paste below

Data sources: `predictions` (closed), `metrics_rolling` (pre-computed where available).

Streamlit components: `st.metric`, `plotly.express.line`, `plotly.express.scatter`, `st.dataframe`, `st.button` triggering `subprocess.run`.

Build: 2 days.

### 4.3 Operator

**Goal**: "Is the scheduler alive, what's the config, can I trigger ad-hoc scans?"

Layout:
- Scheduler status card: systemd state, uptime, next scheduled job times
- Buttons: Restart service, Pause (deferred, v1.1)
- Active config form: `mode` selectbox, version fields, `shadow_skip_telegram` checkbox → "Save + commit + restart" button
- Manual trigger buttons: predict_scan, validate_pending, shadow_status, ship_criteria_check
- Output panel (streaming logs from the subprocess)
- Recent logs panel: `journalctl -u crypto-predictor-scheduler -n 100`, auto-refresh 10 s

Data sources: `systemctl status` via subprocess, `scheduler_config.yaml` file read, `journalctl --output=json` for log streaming.

Streamlit components: `st.button`, `st.code` (for logs), `st.form` (config), `st.selectbox`, `st.toast` (confirm dialogs).

Security: every destructive button requires a confirm modal (`st.modal` with "Type CONFIRM to proceed"). Cloudflare Access is the outer layer; this is the inner safety.

Build: 1 day.

### 4.4 Ask Claude

**Goal**: "Mobile-first AI assistant. Ask questions about predictions, calibration, intel-hub data from anywhere."

Layout:
- Conversation pane (full-width, scrollable) using `st.chat_message`
- Input row: `st.chat_input` at the bottom, "Send" button
- Session card (sidebar or top): session UUID, token usage so far, cost today, "Clear conversation" / "Export markdown" buttons

Backend:
- `pip install anthropic claude-agent-sdk` on the server
- Model: `claude-opus-4-7` (latest stable; we'll re-evaluate on each release)
- Tools (Claude Agent SDK):
  - `query_predictions(filters: dict) -> list[dict]` — PG query helper
  - `query_completeness_breakdown(window_days: int) -> dict` — aggregate
  - `query_calibration_state(version: str) -> dict` — JSON read
  - `run_ship_criteria_check() -> dict` — subprocess
  - `query_intel_hub(category: str, hours_back: int) -> list[dict]` — read whale_txs/news_feed
  - `read_journal(section_regex: str) -> str` — `grep -A` on the session journal
- System prompt: "You are the crypto-predictor assistant. You can query the DB, read the journal, and run analysis scripts. Be terse and data-driven. Surface uncertainty. Never make trading recommendations — describe what the model says, not what the user should do."
- Prompt caching: project context (key journal sections, CLAUDE.md, recent commits) cached as the prefix → 90% cost reduction per turn after the first
- Session continuity: every turn (user + assistant + tool calls) persisted to `claude_chat_log`. Session id is a cookie; reload restores the conversation.
- Cost guardrail: env var `CLAUDE_DAILY_USD_LIMIT=5` (default). If today's total in `claude_chat_log` exceeds the limit, chat input is disabled with a banner "Daily limit reached. Reset at 00:00 UTC."

Streamlit components: `st.chat_message`, `st.chat_input`, `st.spinner`, `st.code` for tool-call output, `st.metric` for session totals.

Build: 2 days.

### Total v1.0 build budget

| Component | Days |
|---|---|
| Shell + global auth + PG pool + Streamlit setup | 1 |
| Dashboard | 2 |
| Track Record | 2 |
| Operator | 1 |
| Ask Claude | 2 |
| Smoke + polish + Hetzner deploy | 1 |
| **Total** | **9 days** |

Migration day (~3.5 h) sits outside this 9-day estimate. Combined: **~10–11 days of subagent-driven dev**.

---

## §5 — Out of scope (v1.0)

| Item | Why deferred | Target version |
|---|---|---|
| Per-prediction drill-down screen | Dashboard click-through; click handler shows toast in v1.0 | v1.1 |
| Manual annotations form | Schema present; form UI postponed | v1.2 |
| Live signals / WebSocket price stream | New systemd service + async ccxt; not blocking | v1.3 |
| Portfolio P&L screen | Holdings table schema present; UI postponed | v1.2 |
| Exchange balance polling job | Cron + ccxt.fetch_balance | v1.2 |
| Per-prediction drill-down auto-Claude analysis | "Ask Claude" is manual; integrated auto-analysis later | v1.3 |
| Multi-user / shared dashboard | Solo user, allowlist of one | — |
| Mobile native app | Streamlit's responsive default suffices | — |
| GitHub Actions auto-deploy | `git pull && systemctl restart` adequate solo | v1.2+ |
| Offsite backup (S3 / B2) | Hetzner snapshot + nightly local backup adequate initially | v1.2 |
| SLOs / pager rotation | Solo, Telegram alerts sufficient | — |
| Trading execution (auto-buy/sell) | Strictly display + manual annotation | — |
| SMS / phone alerts | Telegram suffices | — |
| Per-tool rate limit on Ask Claude | Hard daily $ cap exists; per-tool only if abuse surfaces | conditional |
| Cron-jobs admin panel | Operator screen handles the few buttons we need | — |
| A/B testing framework (parallel model versions) | v0.3 ship + post-monitoring + 3-of-7 auto-rollback already cover this | — |
| Real-time collaboration | Solo | — |
| Email reports | Telegram + UI suffices | — |

---

## §6 — Operations: deploy, secrets, backup

### Deploy workflow (manual, v1.0)

```bash
# From local laptop (any session):
ssh crypto-predictor "cd /opt/crypto-predictor && git pull && \
  sudo systemctl restart crypto-predictor-scheduler && \
  sudo systemctl restart crypto-predictor-ui"
```

Sudo entries (visudo, allows only the two restarts without password):
```
crypto-predictor ALL=(root) NOPASSWD: /bin/systemctl restart crypto-predictor-scheduler
crypto-predictor ALL=(root) NOPASSWD: /bin/systemctl restart crypto-predictor-ui
crypto-predictor ALL=(root) NOPASSWD: /bin/systemctl restart crypto-predictor-intel-bridge
crypto-predictor ALL=(root) NOPASSWD: /bin/systemctl status crypto-predictor-*
```

### Secrets

- `/etc/crypto-predictor/secrets.env`, mode 640, owned by `root:crypto-predictor`
- Required keys: `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `NEWSAPI_API_KEY`, `ANTHROPIC_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`
- Optional: `LUNARCRUSH_API_KEY`, `CLAUDE_DAILY_USD_LIMIT`
- Loaded into systemd services via `EnvironmentFile=/etc/crypto-predictor/secrets.env`
- Rotated by the user; this spec does not include rotation automation

### Backup

- Daily `pg_dump crypto_predictor | gzip > /var/lib/crypto-predictor/backups/pg_$(date +%F).sql.gz` via cron at 07:00 UTC (after the scheduler's nightly cycle)
- Daily `rsync -a data/history/ /var/lib/crypto-predictor/backups/history/` to mirror parquets
- Retention: 14 days local
- Restore: documented in `docs/runbooks/restore-from-backup.md` (written during v1.0 build, tested once before ship)

### SSH access for the agent

- `crypto-predictor` deploy user, ed25519 public key from the user's `~/.ssh/hetzner_key.pub`
- User's local `~/.ssh/config` adds an alias `crypto-predictor` pointing at the server IP
- The agent's Bash tool can run any `ssh crypto-predictor "..."` command
- Sudo restricted to the three service restarts above; all other privileged work requires the user's intervention (apt install, nginx edits, etc.)

---

## §7 — Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Hetzner provisioning held for manual review | Low | 2–4 h delay | Order the day before cutover so it's already done |
| Cloudflare DNS propagation delay (> 1 h) | Low | UI unreachable but scheduler still local | DNS changes go first, cloudflared on standby |
| `ANTHROPIC_API_KEY` cost runaway (> $50/mo) | Medium | Wallet bleed | Hard cap via `CLAUDE_DAILY_USD_LIMIT`; Streamlit cost meter visible on Ask Claude tab |
| SSH key compromised | Low | Full server access by attacker | Use passphrase on the key; Hetzner panel rotates compromised key in 5 min |
| Streamlit perf insufficient (>10k rows, custom layouts) | Medium | Slow / crashing UI | v2.0 React+FastAPI port is planned as the exit path; v1.0 paginates large tables |
| `crypto-intel-hub` MCP Linux compat issue | Medium | Bridge fails; whale_txs/news_feed empty | Test on day 1; if broken, dashboard ships without intel-hub data, fix in v1.1 |
| Windows scheduler still running during migration → double-fire | Medium | Two predictions per symbol per scan, two Telegram alerts | First action of cutover phase is `Stop-ScheduledTask`; documented as T-30 prep |
| Cloudflare Access misconfigured → user locked out | Low | Cannot reach UI | Setup includes a recovery code; Hetzner CLI can disable the tunnel and expose 8501 directly |
| Postgres tuning insufficient (4 GB RAM) | Medium | Slow queries / OOM during simultaneous scan + UI usage | Upgrade path to CPX21 (€7/mo, 8 GB RAM) is one-click in Hetzner panel |
| Backup recovery untested | High (default for new infra) | Hard recovery in a real incident | First week includes a smoke restore: dump → fresh VPS → verify row counts |
| Telegram bot rate limit | Low | Messages dropped | `python-telegram-bot` library handles rate limits already; v0.2.1 baseline shows no issue |
| Streamlit session lost on mobile sleep | Medium | Ask Claude conversation resets | Conversation persisted to `claude_chat_log`, session_id in cookie restores |
| Hetzner snapshot fails | Low | Manual recovery 30 min longer | Nightly `pg_dump` + parquet rsync as belt-and-suspenders |
| TLS cert expires | None | — | Cloudflare Tunnel manages certs end-to-end |
| Agent (Claude Code) unavailable during cutover | Medium | User performs setup alone | All commands are pre-written in the implementation plan; user can run sequentially |
| ANTHROPIC_API_KEY billing surprise after free credits | Medium | Bill arrives | Daily $ cap is the budget guardrail; monthly review of Ask Claude cost meter |

---

## §8 — Success criteria

### Ship blockers (must be true before announcing v1.0)

- [ ] Cloudflare Access magic-link auth lets the user reach the UI from a mobile browser
- [ ] Telegram heartbeat originates from the Hetzner server (Windows scheduler is stopped)
- [ ] `predict_scan` fires at 06:00 UTC on Hetzner, persisting `mode='shadow'` rows
- [ ] PG row counts match Windows pre-migration snapshot
- [ ] All 4 UI screens render and behave correctly
- [ ] Ask Claude answers a real question end-to-end (logged in `claude_chat_log`, cost recorded)
- [ ] Operator → "Save + commit + restart" config flip works (test: shadow → shadow no-op restart)
- [ ] Nightly `pg_dump` + restore-to-fresh-VPS smoke test passes once
- [ ] Backup chain documented: Hetzner snapshot enabled + local pg_dump + parquet rsync

### v1.0 "shipped" definition

- All 4 screens functional + responsive (mobile + desktop)
- Scheduler ran 24 hours uninterrupted on Hetzner with at least one full Telegram heartbeat cycle
- Ask Claude answered at least one real question (e.g., "Show today's top 3 long with their composite scores")
- The v0.3 calibration revision workflow can be executed end-to-end on Hetzner (refit + ship_criteria_check + manual config flip from the Operator screen)

---

## §9 — Open questions for the implementation plan

These will be resolved when `writing-plans` is invoked:

1. Exact systemd unit `Restart=on-failure` semantics + `RestartSec=` value (probably 30s; needs validation)
2. Whether to use `psycopg_pool.ConnectionPool` or SQLAlchemy + asyncpg for the Streamlit-side PG access (Streamlit isn't async-first; sync probably wins)
3. Streamlit auto-refresh implementation (st.autorefresh from `streamlit-autorefresh` package vs JS hack vs full-page refresh button)
4. crypto-intel-hub bridge: run MCP servers as systemd services on the box, or call them via `python -m crypto_intel_hub.servers.X` directly each poll? (former is cleaner)
5. Cloudflare Access provisioning script — can it be done via the cloudflared CLI, or must it be panel-clicked? (panel for v1.0; CLI later)
6. `gitignore` updates: ensure `/var/lib/crypto-predictor/` and `/etc/crypto-predictor/` aren't accidentally committed if the user runs `git add -A` in those dirs

---

## §10 — Relationship to v0.3 calibration revision

The v0.3 plan (`docs/superpowers/plans/2026-06-03-v0.3-calibration-revision.md`) is already implemented (Tasks 1–10 shipped commits `ced7a04`..`c13ab36`). It executes on shadow data accumulated by the scheduler. The migration in this spec preserves all shadow data via the SQLite → PG transfer, so:

- Shadow data continues accumulating uninterrupted on Hetzner
- Day-14 refit (`scripts/refit_calibration_v03.py`) runs on Hetzner against the PG `predictions` table (script needs a small change: accept `DATABASE_URL` env var instead of hard-coded SQLite path)
- Ship-criteria check + promotion runbook unchanged, executed via the Operator screen's "Run ship_criteria_check.py" button

The 14-day clock keeps ticking through the migration. Migration day costs zero shadow days.
