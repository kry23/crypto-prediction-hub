"""Analyze the per-regime isotonic calibration map for ceiling artifacts.

Background: when multiple coins predict the same direction with very similar
direction-raw scores, the isotonic mapping pegs them all to the same calibrated
probability. If the top of the calibration curve plateaus, every coin in that
top bin tops out at the same `p_direction` — making them indistinguishable in
the composite ordering except by their magnitude estimate.

User observation: "5 coins tied at P=0.92" — this script characterizes the
map's ceiling and reports how many coins in the current `predictions.db`
hit it.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


def load_calibration(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def regime_ceiling(reg_map: dict) -> tuple[float, int, float]:
    """Return (max_y, n_knots_at_max_y, x_where_first_reached)."""
    xs = reg_map["x"]
    ys = reg_map["y"]
    max_y = max(ys)
    eps = 1e-9
    at_max = [i for i, y in enumerate(ys) if abs(y - max_y) < eps]
    first_x = xs[at_max[0]] if at_max else float("nan")
    return max_y, len(at_max), first_x


def histogram(ys: list[float], bins: int = 20) -> list[tuple[float, float, int]]:
    if not ys:
        return []
    lo, hi = min(ys), max(ys)
    if hi == lo:
        return [(lo, hi, len(ys))]
    width = (hi - lo) / bins
    counts = [0] * bins
    for y in ys:
        idx = min(int((y - lo) / width), bins - 1)
        counts[idx] += 1
    return [(lo + i * width, lo + (i + 1) * width, counts[i])
            for i in range(bins)]


def ascii_bar(count: int, max_count: int, width: int = 30) -> str:
    if max_count == 0:
        return ""
    return "#" * int(round(count / max_count * width))


def report_calibration(path: Path) -> dict[str, dict]:
    """Print summary for each regime, return dict of stats."""
    cal = load_calibration(path)
    print(f"Calibration file: {path}")
    print(f"Fit window: {cal.get('fit_window', 'n/a')}")
    print()

    stats: dict[str, dict] = {}
    for regime, reg_map in cal["regimes"].items():
        xs = reg_map["x"]
        ys = reg_map["y"]
        max_y, n_at_max, first_x = regime_ceiling(reg_map)
        floor_y = min(ys)
        stats[regime] = {
            "n_knots": len(xs),
            "x_range": (min(xs), max(xs)),
            "y_range": (floor_y, max_y),
            "n_knots_at_ceiling": n_at_max,
            "first_x_at_ceiling": first_x,
        }
        print(f"=== {regime} ===")
        print(f"  knots:         {len(xs)}")
        print(f"  x range:       [{min(xs):+.4f}, {max(xs):+.4f}]")
        print(f"  y range:       [{floor_y:.4f}, {max_y:.4f}]")
        print(f"  knots at floor: {sum(1 for y in ys if y == floor_y)}")
        print(f"  knots at ceiling ({max_y:.4f}): {n_at_max}  "
              f"(first reached at x={first_x:+.4f})")

        print(f"  y histogram (20 bins):")
        hist = histogram(ys, bins=20)
        max_c = max(c for _, _, c in hist) if hist else 0
        for lo, hi, c in hist:
            print(f"    [{lo:.4f}, {hi:.4f})  {c:>3}  "
                  f"{ascii_bar(c, max_c)}")
        print()

    return stats


def count_at_ceiling_in_predictions(db_path: Path,
                                     ceilings: dict[str, float],
                                     tolerance: float = 1e-3
                                     ) -> dict[str, list]:
    """For each regime, list predictions with p_direction within tol of ceiling."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    out: dict[str, list] = {reg: [] for reg in ceilings}
    for row in conn.execute("SELECT * FROM predictions"):
        reg = row["regime"]
        ceil = ceilings.get(reg)
        if ceil is None:
            continue
        if abs(row["p_direction"] - ceil) < tolerance:
            out[reg].append(dict(row))
    conn.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibration",
                        type=Path,
                        default=Path("data/calibration_1_5_4.json"))
    parser.add_argument("--db", type=Path, default=Path("predictions.db"))
    parser.add_argument("--tolerance", type=float, default=1e-3)
    args = parser.parse_args()

    stats = report_calibration(args.calibration)
    ceilings = {reg: s["y_range"][1] for reg, s in stats.items()}

    print("=== Predictions sitting at each regime's ceiling ===")
    hits = count_at_ceiling_in_predictions(args.db, ceilings,
                                             tolerance=args.tolerance)
    for reg, items in hits.items():
        print(f"  {reg} (ceiling={ceilings[reg]:.4f}, tol={args.tolerance}): "
              f"{len(items)} predictions")
        for it in sorted(items,
                          key=lambda x: x["composite_score"], reverse=True):
            print(f"    {it['symbol']:24}  p={it['p_direction']:.4f}  "
                  f"er={it['target_value']:+.4f}  "
                  f"flag={it['confidence_flag']:9}  side={it['prediction']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
