# Post-cutover day — first cycle verify + model root-cause + falling-knife guard (2026-06-06/07)

Continues from `2026-06-05-full-session-journal.md` §29 (cloud cutover to Hostinger / krypredictor.com). This is the day after: verifying the first live daily cycle on the cloud box, a small UI fix, and — the substantive part — investigating the shadow model's alarming hit rate and shipping a fix.

Server clock is UTC; the user works in Europe/Istanbul (UTC+3), so "06-07" in the user's day == "06-06 evening" UTC. Timestamps below are UTC.

---

## §30 First daily cycle on the cloud box — verified green

The cutover's definition-of-done was "tomorrow's 06:00 UTC scheduler cycle fires from the server." It did:

- **06-06 06:00:34** `daily_scan_done` n_predictions=343 → **06:00:35** `predict_scan_done` 343. First server scan ✓.
- **06-06 06:30:03** `validate_pending_done` **n_closed=684**. First validation ✓ — the shadow backlog finally started closing.
- **06-06 07:02** the one-shot health-check routine (`trig_01U2Y9UmH71...`) fired (`run_once_fired`).
- All 5 services `active`, 0 restarts, uptime continuous since cutover (no reboot — earlier "1d 1:51" uptime is from the 06-05 19:43 UTC cutover boot; I briefly misread the user's local June 7 as a server reboot, corrected via `date -u`).
- Backups: `pg_2026-06-05` + `pg_2026-06-06` dumps present; sync + backup timers healthy.

**Windows Task Scheduler can now be uninstalled** (cycle confirmed) — still only *disabled* as the rollback fallback; decommission is the remaining A4 step.

## §31 Dashboard regime "unknown" fix (commit `94d8b23`)

Dashboard showed `REGIME: unknown` while scans logged CHOP. Root cause: `_current_regime()` read the `regime_log` table, which is **defined but never INSERTed by the pipeline** (dead table). The real per-scan regime lives on each `predictions.regime` row (today: CHOP ×343). Fixed `_current_regime()` to read the latest prediction's regime instead. Mock-based query tests unaffected (single fetchone, table-agnostic). 8/8 dashboard tests green.

Also this session: declared the missing `plotly` dep (`0acfdbd` — Track Record crashed `ModuleNotFoundError`); AG-Grid dark tables via `theme="streamlit"` (`0f5a3c4` — st_aggrid 1.2 uses AG-Grid's new Theming API, so the old `.ag-theme-alpine` custom_css did nothing; the earlier white-table attempts `6415c03`/`f8a8c39` were superseded); nginx now injects the `Cf-Access-Authenticated-User-Email` header so `auth.py` is satisfied behind basic-auth.

## §32 Shadow hit-rate investigation — 27.4%, confidently inverted

First real closed data (632 shadow predictions) surfaced an alarming number: **27.4% directional hit rate**, Brier 0.364, and **inverted calibration** — the higher the confidence bucket, the worse the realized rate (bucket [0.70,0.75): expected 73% → realized **4%**).

Ran systematic-debugging (skill). Evidence, in order:

1. **Validation is provably correct.** `validator.py`: `correct = (prediction=="up" and actual>0) or (prediction=="down" and actual<0)`; `actual_outcome` = the symbol's realized log return. The `(prediction,status)→avg actual_outcome` table is 100% consistent (up+correct = +5.4%, up+incorrect = −6.3%, etc.). The **down side is well-calibrated** (predicted −3.3% ≈ actual −3.6%), proving the measurement pipeline works. → **validation-bug hypothesis refuted.**

2. **The asymmetry refutes a global sign-flip.** down (short): 198 preds, **68.7%** hit. up (long): 434 preds, **8.5%** hit, avg predicted +2.7% but avg actual −5.3%. `corr(target_value, actual_outcome) = −0.10` (weak, not a strong global inversion). A sign flip would break the working short side. → **"flip the sign" refuted.**

3. **Decisive feature evidence.** For the 434 failed "up" preds, avg `ret_4h_z = −1.58`, `ret_24h_z = −1.43` (hard-falling coins). For the 198 "down" preds, momentum ~flat. So the model was longing the hardest fallers.

**Root cause (data + code confirmed):**
- `detect_regime()` votes on **BTC 30-day return** (+ funding + global mcap). A sharp ~3-day selloff doesn't move the 30d enough to flip BEAR, so the window stayed classified **CHOP**.
- CHOP applies `MOMENTUM_FLIP_BY_REGIME = −1.0` (mean-reversion). Strongly negative momentum × −1 = strong **UP** signal → the hardest-falling coins became the highest-confidence longs.
- The "chop" was actually a downtrend → the bet-on-the-bounce longs kept falling → 8.5%.

It is a **design flaw, not a code bug** — the code does exactly what it was designed to. Shadow mode did its job: it caught this before any live promotion. (ship_criteria_check correctly = NOT READY.)

## §33 Falling-knife guard (commit `e3bcdd6`, TDD)

User chose remedy B (cap CHOP mean-reversion on extreme-negative momentum). Built via TDD:

- **RED**: 5 failing tests, the key one encoding the bug directly — a crash must not out-long a mild dip (`assert raw_mild > raw_knife` failed: 0.0236 vs 0.175, i.e. the knife scored the stronger long).
- **GREEN**: `FALLING_KNIFE_THRESHOLD = -0.5` + `_effective_momentum_flip(mom, regime)` helper — suppresses the flip to `0.0` when a flip-regime's momentum is below the threshold; mild pullbacks and pumps still mean-revert; BULL/BEAR untouched. `compute_direction_raw_for_regime` refactored to use it (computes `tilt_momentum` once).
- **Verify**: suite 471 → **476** green; deployed; scheduler restarted (cron jobs re-registered, `scheduler_running` UTC); guard confirmed live on server (knife→0.0, mild→−1.0, BULL→1.0). Next 06:00 UTC scan uses it.

**Caveats (honest):** based on ONE 3-day bearish CHOP window. The threshold (−0.5) is tunable and needs cross-regime validation — real (sideways) chop may still want mean-reversion. `calibration_1_5_4.json` was fit on pre-guard `direction_raw`; the v0.3 refit will realign. The guard stops the worst behavior (longing crashes) but does **not** by itself fix the over-bullish bias (434 long / 198 short) or the slow-regime lag — remedies A (fast-downtrend regime guard) and C (long-bias) remain available if data still shows problems.

## §34 Also done + state

- **B5** — Day-14 scripts dry-run on server: `refit_calibration_v03`, `refit_tilt_weights_v03`, `ship_criteria_check` all run cleanly (skip-sparse audit logs, NOT READY result). No mechanical surprises for Day-14.
- **B6** — `v1.0` git tag created + pushed (was on `94d8b23`; the guard `e3bcdd6` lands after it — consider a `v1.0.1` tag when the model work stabilizes).

### Open follow-ups
1. **Watch the guard's effect** — does the long hit rate recover as shadow data accumulates? Re-check in a few days; tune `FALLING_KNIFE_THRESHOLD`.
2. **A4** — uninstall the disabled Windows Task Scheduler (cycle confirmed).
3. **Cross-regime data** before any live promote; revisit remedies A/C if the long side is still weak in true chop.
4. **C7 (v1.1)** — PG-native pipeline conversion (retire the SQLite→PG bridge).

## §35 UI tooling: Journal page, journaling hook, Architecture diagram

Three user-driven additions after the model fix:

- **Journal page** (`1f3fd9d`, spec `d23f932`) — new **📓 Journal** tab renders `docs/sessions/*.md` (date from filename, title from first H1) newest-first plus CHANGELOG, each in a collapsible expander (newest expanded). Pure `journal_loader.load_log_entries()` with **11 TDD tests**; thin page. Behind the existing nginx auth (journals hold server internals, so the page must stay gated).
- **Journaling reminder hook** (global `~/.claude/`, NOT in the repo) — a `Stop` hook (`~/.claude/hooks/journal-reminder.sh` + `~/.claude/settings.json`) that nudges (non-blocking `systemMessage`, fail-open) whenever crypto-predictor has commits newer than the last `docs/sessions/` entry. Set up because the user kept manually reminding me to journal — now harness-enforced. **This very entry was prompted by that hook firing — dogfood success.**
- **Architecture page** (`9e626cf`) — new **🗺 Architecture** tab, `st.graphviz_chart` DOT of the live system: request path (browser → Cloudflare → tunnel → nginx → Streamlit → PG) + pipeline (scheduler → SQLite source-of-truth → 10-min sync bridge → PG mirror), highlighting the v1.0 SQLite/PG split and the v1.1 bridge retirement. No new dependency (DOT string).

Nav is now **6 tabs**: Dashboard · Track Record · Journal · Architecture · Operator · Ask Claude. Suite **476 → 487** (+11 journal_loader).

---

*Commits this day: `0acfdbd` plotly dep · `6415c03`/`f8a8c39`/`0f5a3c4` AG-Grid theming · `94d8b23` regime fix · `e3bcdd6` falling-knife guard · `1f3fd9d` Journal page · `9e626cf` Architecture page. v1.0 tag pushed. Suite 487 green.*
