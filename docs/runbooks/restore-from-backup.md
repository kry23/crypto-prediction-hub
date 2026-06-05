# Restore from backup

Backups are produced nightly at 07:00 UTC by `crypto-predictor-backup.timer`
(script: `deploy/backup.sh`) into `/var/lib/crypto-predictor/backups/`:

```
/var/lib/crypto-predictor/backups/
├── pg/        pg_YYYY-MM-DD.sql.gz      (full PostgreSQL dump, 14-day retention)
├── sqlite/    predictions_YYYY-MM-DD.db (+ sentiment_cache_, global_cache_)
└── history/   <mirror of data/history/> (parquet price/feature store)
```

**Which one matters when?** During the v1.0 bridge era the **SQLite DBs are the
pipeline's source of truth**; PG is a mirror the UI reads (plus the PG-only mart
tables: `whale_txs`, `news_feed`, `claude_chat_log`, `manual_annotations`). So:

- Restoring the **pipeline** → restore the **SQLite** DBs + `history/`.
- Restoring the **UI / mart tables** → restore the **pg** dump.
- A full disaster recovery restores all three.

All commands run on the server. SSH in first: `ssh crypto-predictor` (or
`ssh -i ~/.ssh/hetzner_key root@<IP>` for root).

---

## 1. Restore the SQLite DBs (pipeline source of truth)

```bash
sudo systemctl stop crypto-predictor-scheduler crypto-predictor-sync.timer
cd /opt/crypto-predictor
D=2026-06-06   # pick the dated backup you want

cp /var/lib/crypto-predictor/backups/sqlite/predictions_${D}.db     predictions.db
cp /var/lib/crypto-predictor/backups/sqlite/sentiment_cache_${D}.db data/sentiment_cache.db
cp /var/lib/crypto-predictor/backups/sqlite/global_cache_${D}.db    data/global_cache.db

sudo systemctl start crypto-predictor-scheduler crypto-predictor-sync.timer
```

The next sync tick (≤10 min) re-mirrors the restored SQLite into PG.

## 2. Restore the parquet history

```bash
rsync -a /var/lib/crypto-predictor/backups/history/ /opt/crypto-predictor/data/history/
```

## 3. Restore PostgreSQL (UI + mart tables)

Full clobber of the live DB (use when PG is corrupt or for DR). The pipeline is
unaffected (it reads SQLite); this only rebuilds what the UI reads.

```bash
set -a; . /etc/crypto-predictor/secrets.env; set +a   # DATABASE_URL
D=2026-06-06

# Drop + recreate the schema, then load the dump:
gunzip -c /var/lib/crypto-predictor/backups/pg/pg_${D}.sql.gz | psql "$DATABASE_URL"

sudo systemctl restart crypto-predictor-ui
```

If only the **mart tables** are needed (pipeline tables are fine via the bridge),
restore selectively:

```bash
gunzip -c /var/lib/crypto-predictor/backups/pg/pg_${D}.sql.gz \
  | pg_restore --data-only -t whale_txs -t news_feed -t claude_chat_log ... 2>/dev/null
# (pg_dump here is plain-SQL gzip, so prefer the full psql load above unless you
#  hand-extract table sections.)
```

---

## Restore smoke test (run after first backup, then quarterly)

Proves a dump actually restores. Non-destructive — uses a throwaway DB.

```bash
set -a; . /etc/crypto-predictor/secrets.env; set +a
LATEST=$(ls -t /var/lib/crypto-predictor/backups/pg/pg_*.sql.gz | head -1)
echo "testing: $LATEST"

# Build an admin URL to the default 'postgres' db (same creds, same host):
ADMIN_URL=$(echo "$DATABASE_URL" | sed 's#/crypto_predictor$#/postgres#')

psql "$ADMIN_URL" -c "DROP DATABASE IF EXISTS test_restore;"
psql "$ADMIN_URL" -c "CREATE DATABASE test_restore OWNER crypto_predictor;"
TEST_URL=$(echo "$DATABASE_URL" | sed 's#/crypto_predictor$#/test_restore#')
gunzip -c "$LATEST" | psql "$TEST_URL" >/dev/null
echo "predictions rows in restored dump:"
psql "$TEST_URL" -tAc "SELECT COUNT(*) FROM predictions;"
psql "$ADMIN_URL" -c "DROP DATABASE test_restore;"
```

Row count should match production (`psql "$DATABASE_URL" -tAc "SELECT COUNT(*) FROM predictions;"`).

---

## Provider-level snapshot (recommended companion)

These backups live on the **same droplet** — a disk/instance loss takes them too.
For real DR, enable Hostinger's snapshot/backup add-on (panel → VPS → Backups).
Offsite S3/B2 sync is deferred to v1.2 (spec §5).
