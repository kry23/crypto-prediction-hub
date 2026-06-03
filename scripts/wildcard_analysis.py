"""Characterize wild-card predictions vs NORMAL/HIGH_CONV and report hit rate.

Wild cards = anomaly-flagged predictions (extreme features), routed to their
own bucket by the ranker (`orchestrator/ranker.py`) and excluded from top-K
long/short.

This script answers:
- How many wild cards exist right now? What's their regime / direction mix?
- How does their profile (p_direction, expected return, composite score)
  compare to NORMAL and HIGH_CONV?
- For closed wild cards, what's the realized hit rate? Does the bucket
  outperform NORMAL or is it noise?

Usage: `python scripts/wildcard_analysis.py [--db predictions.db]`
"""
from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path


def fetch_predictions(db_path: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM predictions").fetchall()
    conn.close()
    return rows


def profile_by_flag(rows: list[sqlite3.Row]) -> dict[str, dict]:
    """Aggregate p/expected-return/composite stats per confidence_flag."""
    buckets: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        buckets.setdefault(r["confidence_flag"], []).append(r)
    out: dict[str, dict] = {}
    for flag, items in buckets.items():
        ps = [r["p_direction"] for r in items]
        ets = [abs(r["target_value"]) for r in items]
        comps = [r["composite_score"] for r in items]
        out[flag] = {
            "n": len(items),
            "avg_p": sum(ps) / len(ps),
            "avg_abs_er": sum(ets) / len(ets),
            "avg_comp": sum(comps) / len(comps),
        }
    return out


def hit_rate_by_flag(rows: list[sqlite3.Row]) -> dict[str, dict]:
    """Compute realized hit rate per flag, only for closed predictions."""
    out: dict[str, dict] = {}
    for r in rows:
        if r["status"] == "pending":
            continue
        d = out.setdefault(r["confidence_flag"],
                            {"closed": 0, "correct": 0, "incorrect": 0,
                             "indeterminate": 0})
        d["closed"] += 1
        ev = r["evaluation"]
        if ev == "correct":
            d["correct"] += 1
        elif ev == "incorrect":
            d["incorrect"] += 1
        else:
            d["indeterminate"] += 1
    for d in out.values():
        d["hit_rate"] = (d["correct"] / max(d["closed"], 1)
                          if d["closed"] else 0.0)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("predictions.db"))
    args = parser.parse_args()

    rows = fetch_predictions(args.db)
    print(f"Total predictions in DB: {len(rows)}")
    print()

    flag_status = Counter((r["confidence_flag"], r["status"]) for r in rows)
    print("=== confidence_flag x status ===")
    for (flag, status), n in sorted(flag_status.items()):
        print(f"  {flag:12} {status:10} {n:4}")
    print()

    wild = [r for r in rows if r["confidence_flag"] == "WILD_CARD"]
    print(f"=== Wild card population: {len(wild)} ===")
    print(f"  regime mix : {dict(Counter(r['regime'] for r in wild))}")
    print(f"  direction  : {dict(Counter(r['prediction'] for r in wild))}")
    print(f"  status     : {dict(Counter(r['status'] for r in wild))}")
    print()

    prof = profile_by_flag(rows)
    print("=== Profile by confidence_flag ===")
    print(f"  {'flag':12} {'n':>4}  {'avg p':>7}  {'avg |er|':>9}  "
          f"{'avg comp':>9}")
    for flag, d in sorted(prof.items()):
        print(f"  {flag:12} {d['n']:>4}  {d['avg_p']:>7.4f}  "
              f"{d['avg_abs_er']:>9.4f}  {d['avg_comp']:>9.4f}")
    print()

    print("=== Top wild cards by composite score ===")
    for r in sorted(wild, key=lambda r: r["composite_score"], reverse=True):
        print(f"  {r['symbol']:24}  p={r['p_direction']:.3f}  "
              f"er={r['target_value']:+.4f}  comp={r['composite_score']:.4f}  "
              f"{r['prediction']:5}  {r['status']}")
    print()

    hr = hit_rate_by_flag(rows)
    if any(d["closed"] for d in hr.values()):
        print("=== Realized hit rate by flag (closed predictions only) ===")
        print(f"  {'flag':12} {'closed':>7}  {'correct':>8}  {'wrong':>6}  "
              f"{'indet':>6}  {'hit rate':>9}")
        for flag, d in sorted(hr.items()):
            print(f"  {flag:12} {d['closed']:>7}  {d['correct']:>8}  "
                  f"{d['incorrect']:>6}  {d['indeterminate']:>6}  "
                  f"{d['hit_rate']:>8.1%}")
    else:
        print("=== Hit rate: cannot measure yet ===")
        print("    All predictions still pending. Re-run after validate_pending "
              "closes them at ~T+24h.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
