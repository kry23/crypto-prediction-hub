-- =====================================================================
-- crypto-predictor v1.0 initial schema for PostgreSQL 16
-- =====================================================================
-- Applied by scripts/init_postgres_schema.py during cutover, BEFORE
-- scripts/migrate_sqlite_to_postgres.py copies data over.
--
-- Idempotent: every CREATE TABLE / CREATE INDEX uses IF NOT EXISTS so
-- re-running on a populated DB is a no-op.
--
-- Column types track scripts/migrate_sqlite_to_postgres.py:TYPE_UPLIFT
-- exactly. PG reserved words ("window") are double-quoted.
-- Source of truth: docs/superpowers/specs/2026-06-05-web-ui-cloud-migration-design.md §3
-- =====================================================================

-- ---------------------------------------------------------------------
-- Migration tracker (consumed by scripts/init_postgres_schema.py)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS _migrations (
    version     VARCHAR(40) PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sha256      VARCHAR(64) NOT NULL
);

-- =====================================================================
-- Migrated tables (1:1 from predictions.db, with PG type uplifts)
-- =====================================================================

-- ---------------------------------------------------------------------
-- predictions  --  one row per scored symbol per scan
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS predictions (
    id                   VARCHAR(40) PRIMARY KEY,
    symbol               VARCHAR(40) NOT NULL,
    horizon_hours        INTEGER NOT NULL DEFAULT 24,
    prediction           VARCHAR(10) NOT NULL
                         CHECK (prediction IN ('up', 'down')),
    p_direction          NUMERIC(10, 8) NOT NULL,
    target_value         NUMERIC(20, 8) NOT NULL,
    composite_score      NUMERIC(10, 8) NOT NULL,
    confidence_flag      VARCHAR(20)
                         CHECK (confidence_flag IN ('NORMAL', 'HIGH_CONV', 'WILD_CARD')),
    regime               VARCHAR(20) NOT NULL
                         CHECK (regime IN ('BULL', 'CHOP', 'BEAR')),
    formula_version      TEXT NOT NULL,
    calibration_version  TEXT NOT NULL,
    status               VARCHAR(20) NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'correct', 'incorrect',
                                            'expired', 'skipped')),
    actual_outcome       NUMERIC(20, 8),
    error_margin         NUMERIC(20, 8),
    evaluation           TEXT,
    created_at           TIMESTAMPTZ NOT NULL,
    validated_at         TIMESTAMPTZ,
    mode                 VARCHAR(20) NOT NULL DEFAULT 'live'
                         CHECK (mode IN ('live', 'shadow', 'backtest')),
    feature_completeness VARCHAR(20) NOT NULL DEFAULT 'full'
                         CHECK (feature_completeness IN ('full', 'degraded')),
    missing_features     TEXT
);
CREATE INDEX IF NOT EXISTS idx_pred_symbol               ON predictions(symbol);
CREATE INDEX IF NOT EXISTS idx_pred_status               ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_pred_created              ON predictions(created_at);
CREATE INDEX IF NOT EXISTS idx_pred_regime               ON predictions(regime);
CREATE INDEX IF NOT EXISTS idx_predictions_mode          ON predictions(mode);
CREATE INDEX IF NOT EXISTS idx_predictions_completeness  ON predictions(feature_completeness);

-- ---------------------------------------------------------------------
-- predictions_features  --  feature vector for each prediction
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS predictions_features (
    prediction_id VARCHAR(40) NOT NULL
                  REFERENCES predictions(id) ON DELETE CASCADE,
    feature_name  VARCHAR(80) NOT NULL,
    raw_value     NUMERIC(20, 8),
    z_value       NUMERIC(20, 8),
    PRIMARY KEY (prediction_id, feature_name)
);

-- ---------------------------------------------------------------------
-- calibration_maps  --  persisted regime-specific calibration tables
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calibration_maps (
    version    TEXT NOT NULL,
    regime     VARCHAR(20) NOT NULL,
    map_json   TEXT NOT NULL,
    fit_window TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (version, regime)
);

-- ---------------------------------------------------------------------
-- regime_log  --  daily BULL/CHOP/BEAR label + drivers
-- ---------------------------------------------------------------------
-- NOTE: `date` column is TIMESTAMPTZ to match TYPE_UPLIFT (mapped from ISO 8601
-- text in SQLite); semantically it represents a calendar day in UTC.
CREATE TABLE IF NOT EXISTS regime_log (
    date              TIMESTAMPTZ PRIMARY KEY,
    regime            VARCHAR(20) NOT NULL,
    btc_30d_return    NUMERIC(10, 6),
    btc_funding_avg   NUMERIC(10, 6),
    global_mcap_trend NUMERIC(10, 6)
);

-- ---------------------------------------------------------------------
-- metrics_rolling  --  pre-aggregated KPI cube
-- ---------------------------------------------------------------------
-- NOTE: `window` is a PG reserved keyword (window functions); always quote it.
CREATE TABLE IF NOT EXISTS metrics_rolling (
    "window"        VARCHAR(10) NOT NULL,
    regime          VARCHAR(20) NOT NULL,
    direction       VARCHAR(10) NOT NULL,
    n_predictions   INTEGER,
    n_correct       INTEGER,
    hit_rate        NUMERIC(10, 8),
    mae             NUMERIC(10, 8),
    brier           NUMERIC(10, 8),
    topk_alpha      NUMERIC(20, 8),
    topk_alpha_btc  NUMERIC(20, 8),
    updated_at      TIMESTAMPTZ,
    PRIMARY KEY ("window", regime, direction)
);

-- ---------------------------------------------------------------------
-- patterns  --  named setup library with win-rate stats
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patterns (
    name            VARCHAR(120) PRIMARY KEY,
    conditions      TEXT,
    occurrences     INTEGER NOT NULL DEFAULT 0,
    wins            INTEGER NOT NULL DEFAULT 0,
    losses          INTEGER NOT NULL DEFAULT 0,
    win_rate        NUMERIC(10, 8) NOT NULL DEFAULT 0,
    avg_pnl_percent NUMERIC(20, 8) NOT NULL DEFAULT 0,
    first_seen      TIMESTAMPTZ,
    last_seen       TIMESTAMPTZ,
    recommendation  VARCHAR(20)
                    CHECK (recommendation IN ('SEEK', 'NEUTRAL', 'AVOID')),
    notes           TEXT
);

-- ---------------------------------------------------------------------
-- runs  --  one row per scheduled job invocation
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runs (
    run_id              VARCHAR(80) PRIMARY KEY,
    job                 VARCHAR(40) NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    status              VARCHAR(20)
                        CHECK (status IN ('ok', 'error', 'partial')),
    n_predictions       INTEGER,
    n_errors            INTEGER,
    error_summary       TEXT,
    formula_version     TEXT,
    calibration_version TEXT
);

-- =====================================================================
-- Migrated tables (1:1 from sentiment_cache.db)
-- =====================================================================

CREATE TABLE IF NOT EXISTS sentiment_cache (
    symbol           VARCHAR(40) NOT NULL,
    timestamp        TIMESTAMPTZ NOT NULL,
    news_sent_24h    NUMERIC(10, 6),
    social_sent_24h  NUMERIC(10, 6),
    sent_velocity    NUMERIC(10, 6),
    news_volume_z    NUMERIC(10, 6),
    PRIMARY KEY (symbol, timestamp)
);

-- =====================================================================
-- Migrated tables (1:1 from global_cache.db)
-- =====================================================================

CREATE TABLE IF NOT EXISTS global_cache (
    timestamp         TIMESTAMPTZ PRIMARY KEY,
    btc_dom_trend_7d  NUMERIC(10, 6),
    eth_btc_trend_7d  NUMERIC(10, 6),
    total_mcap_z      NUMERIC(10, 6),
    sector_btc        NUMERIC(10, 6),
    sector_eth        NUMERIC(10, 6),
    sector_defi       NUMERIC(10, 6),
    sector_l1         NUMERIC(10, 6)
);

CREATE TABLE IF NOT EXISTS coin_btc_corr (
    symbol     VARCHAR(40) NOT NULL,
    timestamp  TIMESTAMPTZ NOT NULL,
    corr_30d   NUMERIC(10, 6),
    PRIMARY KEY (symbol, timestamp)
);

-- =====================================================================
-- New mart tables (live web UI + crypto-intel-hub bridge)
-- =====================================================================

-- ---------------------------------------------------------------------
-- A) prices_1m  --  OKX 1m OHLCV mirror (schema present at v1.0, populated v1.3)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prices_1m (
    symbol        VARCHAR(40) NOT NULL,
    ts            TIMESTAMPTZ NOT NULL,
    open          NUMERIC(20, 8),
    high          NUMERIC(20, 8),
    low           NUMERIC(20, 8),
    close         NUMERIC(20, 8),
    volume_quote  NUMERIC(24, 4),
    PRIMARY KEY (symbol, ts)
);
CREATE INDEX IF NOT EXISTS idx_prices_1m_ts ON prices_1m(ts DESC);

-- ---------------------------------------------------------------------
-- B) whale_txs  --  crypto-intel-hub MCP whale bridge feed
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS whale_txs (
    id          BIGSERIAL PRIMARY KEY,
    chain       VARCHAR(20) NOT NULL,
    symbol      VARCHAR(40),
    tx_hash     VARCHAR(80) NOT NULL,
    amount_usd  NUMERIC(20, 2),
    from_label  VARCHAR(120),
    to_label    VARCHAR(120),
    ts          TIMESTAMPTZ NOT NULL,
    raw_json    JSONB NOT NULL,
    UNIQUE (chain, tx_hash)
);
CREATE INDEX IF NOT EXISTS idx_whale_txs_ts ON whale_txs(ts DESC);

-- ---------------------------------------------------------------------
-- C) news_feed  --  crypto-intel-hub news bridge feed
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_feed (
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
CREATE INDEX IF NOT EXISTS idx_news_feed_ts        ON news_feed(ts DESC);
CREATE INDEX IF NOT EXISTS idx_news_feed_category  ON news_feed(category);
CREATE INDEX IF NOT EXISTS idx_news_feed_symbols   ON news_feed USING GIN (symbols_mentioned);

-- ---------------------------------------------------------------------
-- D) manual_annotations  --  schema present at v1.0; form ships v1.2
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS manual_annotations (
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
CREATE INDEX IF NOT EXISTS idx_manual_annotations_symbol
    ON manual_annotations(symbol);
CREATE INDEX IF NOT EXISTS idx_manual_annotations_open
    ON manual_annotations(closed_at) WHERE closed_at IS NULL;

-- ---------------------------------------------------------------------
-- E) portfolio_holdings  --  schema present at v1.0; form ships v1.2
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id            BIGSERIAL PRIMARY KEY,
    asset         VARCHAR(40) NOT NULL,
    quantity      NUMERIC(24, 8) NOT NULL,
    avg_cost_usd  NUMERIC(20, 2),
    venue         VARCHAR(40),
    notes         TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_portfolio_asset ON portfolio_holdings(asset);

-- ---------------------------------------------------------------------
-- F) exchange_balances  --  schema present at v1.0; poller ships v1.2
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exchange_balances (
    id           BIGSERIAL PRIMARY KEY,
    exchange     VARCHAR(40) NOT NULL,
    asset        VARCHAR(40) NOT NULL,
    free         NUMERIC(24, 8),
    used         NUMERIC(24, 8),
    total        NUMERIC(24, 8),
    snapshot_ts  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_exchange_balances_ts
    ON exchange_balances(exchange, asset, snapshot_ts DESC);

-- ---------------------------------------------------------------------
-- G) claude_chat_log  --  Ask Claude tab session log
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claude_chat_log (
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
CREATE INDEX IF NOT EXISTS idx_claude_chat_log_session
    ON claude_chat_log(session_id, created_at);
