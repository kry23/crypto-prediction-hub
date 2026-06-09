# Daily checks + falling-knife guard verdict + remedy A (2026-06-08)

Continues from `2026-06-07-post-cutover-model-fix.md`. Morning ops checks, the first real read on the falling-knife guard, a full backlog review, and shipping remedy A (fast-downtrend regime override). Server clock is UTC.

---

## §36 Daily checks + the guard verdict (nuanced)

Ops all green: server up 2d+, 5 services active 0 restarts, daily cycles firing (06-07 + 06-08 06:00 scan / 06:30 validate), 4 daily pg backups, site 401.

**Falling-knife guard (e3bcdd6, live since 06-06 22:13 UTC) — long/short bias by scan day:**

| scan day | up | down | long % | hit% (closed) |
|---|---|---|---|---|
| 06-04 (pre-guard) | 436 | 248 | 64% | 27.4% |
| 06-05 (pre-guard) | 218 | 125 | 64% | 33.3% |
| 06-06 (pre-guard) | 218 | 125 | 64% | 70.1% |
| **06-07 (guarded)** | 111 | 232 | **32%** | 50.2% |
| **06-08 (guarded)** | 6 | 337 | **2%** | (pending) |

**Verdict is NOT a clean win.** The guard eliminated the falling-knife longs, but combined with the lagging regime detector it swung the model to ~98% short on 06-08 — an over-correction. And hit rate is dominated by that day's market direction (06-06 rose → the over-bullish pre-guard model scored 70%; a tiny single-regime sample). The guard treated the symptom; the root cause — the slow 30d-BTC regime detector mislabeling a downtrend as CHOP — was still open. This pointed straight at remedy A.

## §37 Backlog review

Ran a fan-out review (workflow: journals/specs/plans/code/milestones readers → synthesis). The synthesis + plans agents hit the session usage limit, so I synthesized directly from first-hand context. Prioritized:

- **P0**: remedy A (fast-downtrend regime override) · watch+tune guard/regime thresholds.
- **P1**: A4 Windows decommission (cycle confirmed 3d) · refit calibration post-guard · `regime_log` dead-table cleanup · A3 nginx password.
- **P2 / v1.x**: C7 PG-native pipeline (retire bridge, ~48 files) · Streamlit `use_container_width` deprecation · deferred UI features (drill-down, annotations form, portfolio P&L, live OKX) · ops hardening (offsite backup, snapshot, CI deploy) · `v1.0.1` tag.

State: infra mature; the open frontier is the **model**. No live promotion until model behavior is principled across regimes.

## §38 Remedy A — fast-downtrend regime override (commit `602a6ed`, TDD)

`detect_regime` voted only on the **30d** BTC return (+ funding + mcap); a sharp 7d selloff couldn't flip it to BEAR, so it sat in CHOP. Fix: compute `btc_7d_return`; if it drops below `FAST_DOWNTREND_THRESHOLD` (−0.08) **and** no genuine bull/bear vote majority exists, classify **BEAR**. Subordinate to a real vote majority (a correction in a true bull stays BULL).

- **TDD**: 4 tests (override fires CHOP→BEAR on a rise-then-sharp-drop path; mild dip stays CHOP; strong-bull-with-correction stays BULL; threshold constant). New `_seed_btc_closes` helper for explicit price paths. Suite **487 → 491**.
- **Deployed + scheduler restarted.** Live verification on the server: BTC 30d −26.0%, 7d −10.2% (override fires), regime now **BEAR**. (The market has fallen enough that the 30d also reads bear now; remedy A's value is forward — it catches the *next* fast selloff in days, not weeks.)
- In BEAR the weights are momentum 0.10 (no flip) + technical 0.50, so the model now does **principled trend-following** in a confirmed downtrend instead of the CHOP-mean-reversion-then-guard artifact. Remedy A (CHOP→BEAR) and the falling-knife guard (CHOP-only) are complementary, layered.

### Open follow-ups
1. **Watch the combined effect** (remedy A + guard) as cross-regime data accumulates; tune `FAST_DOWNTREND_THRESHOLD` (−0.08) and `FALLING_KNIFE_THRESHOLD` (−0.5).
2. **Refit calibration** once model direction stabilizes (current `1_5_4` predates both guards).
3. P1/P2 backlog from §37 — A4 decommission next-easiest; C7 PG-native the big v1.1.
4. Day-14 v0.3 ship gated on principled model behavior, not the calendar.

---

*Commits: `602a6ed` remedy A. Suite 491 green. Live regime now BEAR.*
