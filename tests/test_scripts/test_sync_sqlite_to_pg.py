"""Unit tests for the SQLite -> PG sync bridge SQL builder.

These cover the conflict-clause logic without needing a live PostgreSQL; the
end-to-end upsert behaviour is verified against the real server during cutover.
"""
from __future__ import annotations

from scripts.sync_sqlite_to_pg import INSERT_ONLY, build_upsert_sql


def test_mutable_table_emits_do_update_for_non_pk_columns():
    sql = build_upsert_sql("predictions", ["id", "symbol", "status", "created_at"])
    assert "INSERT INTO predictions (id, symbol, status, created_at)" in sql
    assert "ON CONFLICT (id) DO UPDATE SET" in sql
    # non-PK columns are refreshed from the incoming row
    assert "symbol = EXCLUDED.symbol" in sql
    assert "status = EXCLUDED.status" in sql
    assert "created_at = EXCLUDED.created_at" in sql
    # the PK column itself is never in the SET list
    assert "id = EXCLUDED.id" not in sql


def test_status_update_propagates_via_excluded():
    # The whole point of the bridge: a validated row's status must update in PG.
    sql = build_upsert_sql("predictions", ["id", "status", "validated_at"])
    assert "ON CONFLICT (id) DO UPDATE SET" in sql
    assert "status = EXCLUDED.status" in sql
    assert "validated_at = EXCLUDED.validated_at" in sql


def test_predictions_features_is_insert_only():
    assert "predictions_features" in INSERT_ONLY
    sql = build_upsert_sql(
        "predictions_features", ["prediction_id", "feature_name", "raw_value"]
    )
    assert "ON CONFLICT (prediction_id, feature_name) DO NOTHING" in sql
    assert "DO UPDATE" not in sql


def test_all_pk_columns_falls_back_to_do_nothing():
    # If every column is part of the PK there is nothing non-key to update.
    sql = build_upsert_sql("regime_log", ["date"])
    assert "ON CONFLICT (date) DO NOTHING" in sql
    assert "DO UPDATE" not in sql


def test_composite_pk_and_reserved_word_quoting():
    # metrics_rolling has a composite PK including the reserved word "window".
    sql = build_upsert_sql(
        "metrics_rolling", ["window", "regime", "direction", "hit_rate"]
    )
    assert 'ON CONFLICT ("window", regime, direction) DO UPDATE SET' in sql
    # reserved word is quoted in the SET clause too
    assert "hit_rate = EXCLUDED.hit_rate" in sql
    # PK members (including quoted "window") are not in the SET list
    assert "regime = EXCLUDED.regime" not in sql
    assert '"window" = EXCLUDED."window"' not in sql


def test_multi_column_upsert_updates_only_non_pk():
    sql = build_upsert_sql(
        "sentiment_cache", ["symbol", "timestamp", "news_sent_24h", "social_sent_24h"]
    )
    assert "ON CONFLICT (symbol, timestamp) DO UPDATE SET" in sql
    assert "news_sent_24h = EXCLUDED.news_sent_24h" in sql
    assert "social_sent_24h = EXCLUDED.social_sent_24h" in sql
    assert "symbol = EXCLUDED.symbol" not in sql
    assert "timestamp = EXCLUDED.timestamp" not in sql
