"""Quick state audit — mode distribution + recent activity."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "predictions.db"
c = sqlite3.connect(str(DB))

print("=== Mode distribution ===")
for m, n in c.execute("SELECT mode, COUNT(*) FROM predictions GROUP BY mode"):
    print(f"  mode={m}  n={n}")

print()
print("=== Recent activity (latest 5 created_at) ===")
for row in c.execute(
    "SELECT mode, COUNT(*), MIN(created_at), MAX(created_at) "
    "FROM predictions GROUP BY mode"
):
    print(f"  mode={row[0]}  n={row[1]}  first={row[2]}  last={row[3]}")

print()
print("=== Latest cron run state ===")
print("  scheduler_config.yaml says shadow, so any new rows should be mode=shadow")
print("  if there are no shadow rows, the predict_scan never fired since v0.2.1 ship")

c.close()
