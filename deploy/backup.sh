#!/usr/bin/env bash
#
# Nightly server backup for crypto-predictor (run by crypto-predictor-backup.timer).
#
# Backs up three things, because the system is split-brain during the v1.0
# bridge era (pipeline writes SQLite; UI + mart tables live in PG):
#   1. pg_dump    -> captures PG-only mart tables (whale_txs, news_feed,
#                    claude_chat_log, manual_annotations) + the mirrored pipeline
#   2. SQLite DBs -> the pipeline's actual source of truth (predictions + caches)
#   3. parquet    -> data/history price/feature store (needed by every scan)
#
# Retention: 14 days for the dated pg/ + sqlite/ dumps. history/ is an rsync
# mirror (current snapshot, not dated).
#
# Runs as the crypto-predictor user; /var/lib/crypto-predictor/backups must be
# owned by it. DATABASE_URL comes from the systemd EnvironmentFile.
#
# NOTE: backups land on the SAME droplet. For true DR, pair this with the
# provider's snapshot feature (spec §5: offsite S3/B2 deferred to v1.2).

set -euo pipefail

BACKUP_ROOT=/var/lib/crypto-predictor/backups
REPO=/opt/crypto-predictor
KEEP_DAYS=14
DATE=$(date -u +%F)   # UTC YYYY-MM-DD

mkdir -p "$BACKUP_ROOT/pg" "$BACKUP_ROOT/sqlite" "$BACKUP_ROOT/history"

# DATABASE_URL: from the systemd EnvironmentFile in production; fall back to
# sourcing the secrets file for manual runs.
if [ -z "${DATABASE_URL:-}" ]; then
    set -a; . /etc/crypto-predictor/secrets.env; set +a
fi

# 1) PostgreSQL dump (gzip)
pg_dump "$DATABASE_URL" | gzip > "$BACKUP_ROOT/pg/pg_${DATE}.sql.gz"

# 2) SQLite source-of-truth DBs — use the online .backup API (consistent even
#    if the scheduler is mid-write; safe across WAL mode).
for db in predictions.db data/sentiment_cache.db data/global_cache.db; do
    if [ -f "$REPO/$db" ]; then
        name=$(basename "$db" .db)
        sqlite3 "$REPO/$db" ".backup '$BACKUP_ROOT/sqlite/${name}_${DATE}.db'"
    fi
done

# 3) Parquet history mirror (current snapshot)
rsync -a --delete "$REPO/data/history/" "$BACKUP_ROOT/history/"

# 4) Retention — prune dated dumps older than KEEP_DAYS
find "$BACKUP_ROOT/pg" -name 'pg_*.sql.gz' -mtime "+$KEEP_DAYS" -delete
find "$BACKUP_ROOT/sqlite" -name '*.db' -mtime "+$KEEP_DAYS" -delete

echo "backup complete: $DATE"
du -sh "$BACKUP_ROOT"/pg "$BACKUP_ROOT"/sqlite "$BACKUP_ROOT"/history 2>/dev/null || true
