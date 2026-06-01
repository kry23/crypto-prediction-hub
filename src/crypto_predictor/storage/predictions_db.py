"""predictions.db — own schema for crypto-predictor (separate from learning-db)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id                  TEXT PRIMARY KEY,
    symbol              TEXT NOT NULL,
    horizon_hours       INTEGER NOT NULL DEFAULT 24,
    prediction          TEXT NOT NULL CHECK (prediction IN ('up','down')),
    p_direction         REAL NOT NULL,
    target_value        REAL NOT NULL,
    composite_score     REAL NOT NULL,
    confidence_flag     TEXT CHECK (confidence_flag IN ('NORMAL','HIGH_CONV','WILD_CARD')),
    regime              TEXT NOT NULL CHECK (regime IN ('BULL','BEAR','CHOP')),
    formula_version     TEXT NOT NULL,
    calibration_version TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','correct','incorrect','expired','skipped')),
    actual_outcome      REAL,
    error_margin        REAL,
    evaluation          TEXT,
    created_at          TEXT NOT NULL,
    validated_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_pred_symbol  ON predictions(symbol);
CREATE INDEX IF NOT EXISTS idx_pred_status  ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_pred_created ON predictions(created_at);
CREATE INDEX IF NOT EXISTS idx_pred_regime  ON predictions(regime);

CREATE TABLE IF NOT EXISTS predictions_features (
    prediction_id TEXT NOT NULL,
    feature_name  TEXT NOT NULL,
    raw_value     REAL,
    z_value       REAL,
    PRIMARY KEY (prediction_id, feature_name),
    FOREIGN KEY (prediction_id) REFERENCES predictions(id)
);

CREATE TABLE IF NOT EXISTS calibration_maps (
    version    TEXT NOT NULL,
    regime     TEXT NOT NULL,
    map_json   TEXT NOT NULL,
    fit_window TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (version, regime)
);

CREATE TABLE IF NOT EXISTS regime_log (
    date              TEXT PRIMARY KEY,
    regime            TEXT NOT NULL,
    btc_30d_return    REAL,
    btc_funding_avg   REAL,
    global_mcap_trend REAL
);

CREATE TABLE IF NOT EXISTS metrics_rolling (
    window         TEXT,
    regime         TEXT,
    direction      TEXT,
    n_predictions  INTEGER,
    n_correct      INTEGER,
    hit_rate       REAL,
    mae            REAL,
    brier          REAL,
    topk_alpha     REAL,
    topk_alpha_btc REAL,
    updated_at     TEXT,
    PRIMARY KEY (window, regime, direction)
);

CREATE TABLE IF NOT EXISTS patterns (
    name            TEXT PRIMARY KEY,
    conditions      TEXT,
    occurrences     INTEGER NOT NULL DEFAULT 0,
    wins            INTEGER NOT NULL DEFAULT 0,
    losses          INTEGER NOT NULL DEFAULT 0,
    win_rate        REAL NOT NULL DEFAULT 0,
    avg_pnl_percent REAL NOT NULL DEFAULT 0,
    first_seen      TEXT,
    last_seen       TEXT,
    recommendation  TEXT CHECK (recommendation IN ('SEEK','NEUTRAL','AVOID')),
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    job                 TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    completed_at        TEXT,
    status              TEXT CHECK (status IN ('ok','error','partial')),
    n_predictions       INTEGER,
    n_errors            INTEGER,
    error_summary       TEXT,
    formula_version     TEXT,
    calibration_version TEXT
);
"""


def init_db(path: Path) -> None:
    """Create predictions.db schema if missing. Idempotent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_table_names(path: Path) -> set[str]:
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()
