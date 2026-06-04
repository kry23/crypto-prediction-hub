"""Quick state audit — mode + completeness + calibration distribution."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "predictions.db"
c = sqlite3.connect(str(DB))

print("=== Mode x completeness x calibration_version ===")
for row in c.execute(
    "SELECT mode, feature_completeness, calibration_version, missing_features, "
    "       COUNT(*) FROM predictions "
    "GROUP BY mode, feature_completeness, calibration_version, missing_features "
    "ORDER BY 1, 2, 3"
):
    missing = row[3] if row[3] is not None else "NULL"
    print(f"  mode={row[0]:8} comp={row[1]:9} cal={row[2]:20} "
          f"missing={missing:20} n={row[4]}")

print()
print("=== Latest shadow row sample ===")
row = c.execute(
    "SELECT id, symbol, created_at, mode, feature_completeness, "
    "       missing_features, calibration_version, regime, p_direction "
    "FROM predictions WHERE mode='shadow' "
    "ORDER BY created_at DESC LIMIT 1"
).fetchone()
if row:
    cols = ["id", "symbol", "created_at", "mode", "completeness", "missing",
            "calibration_version", "regime", "p_direction"]
    for k, v in zip(cols, row):
        print(f"  {k:22} {v}")
else:
    print("  no shadow rows yet")
c.close()
