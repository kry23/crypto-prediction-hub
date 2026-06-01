---
title: crypto-predictor — Design Specification
date: 2026-06-01
version: 0.1-draft
author: Koray Korkmaz (with Claude pair-design)
status: draft, pending user review
related:
  - crypto-intel-hub (Phase 1, ~/.claude/plugins/crypto-intel-hub/)
  - crypto-trading-desk v1.0.0 (hugoguerrap, ~/.claude/plugins/cache/hugoguerrap/crypto-trading-desk/1.0.0/)
---

# crypto-predictor — Design Specification

## 1. Executive Summary

**crypto-predictor** is a heuristic-first probabilistic prediction platform that scans the ~340 OKX Global USDT-perpetual universe every day at 06:00 UTC and produces, for each coin, a **24-hour direction probability** (P↑/P↓) and **expected magnitude** (signed % return), composited into a daily ranking of long and short candidates.

It is the third project in a trio built around an "intel → analyze → predict" theme:
- **crypto-intel-hub** answers *what is happening now* (sentiment, news, prices, alerts).
- **crypto-trading-desk** answers *how does this look technically* (indicators, microstructure, futures data, learning DB).
- **crypto-predictor** (this project) answers *what will happen, with what probability, and were we right last time?*

The system is built around a closed feedback loop (A → B → C in product terms):
- **A** — probabilistic prediction engine (direction + magnitude, calibrated)
- **B** — validation loop with track record, calibration drift detection, monthly recalibration
- **C** — universe-wide daily ranking, output as morning markdown report plus selective Telegram alerts

The math is intentionally **vectorized and explainable** (Phase 1 = weighted heuristic + isotonic calibration); LLM is used only to produce 2–3 sentence summaries for top-40 candidates. Classical ML (gradient boosting) is deferred to v0.3, after 30+ days of live prediction-outcome pairs have accumulated, so it can be trained on honest production data instead of synthetic backtests alone.

The project lives at `C:\Users\Koray\Desktop\crypto-predictor\` and registers as a Claude Code plugin pointing to that path.

---

## 2. Goals and Non-Goals

### Goals (in scope, Phase 1)
- Daily 06:00 UTC batch scan of ~340 OKX-Global USDT perpetuals.
- 24-hour horizon: direction probability + magnitude estimate per coin.
- Universe-wide ranking: top-20 long, top-20 short, plus a separate wild-card list for anomalies.
- Closed feedback loop: every prediction is stored, validated 24h later, and contributes to rolling hit-rate and Brier score metrics.
- Monthly automatic recalibration plus drift detection.
- Per-regime calibration (BULL / BEAR / CHOP).
- Markdown daily report saved to disk + Telegram summary with selective high-conviction alerts.
- Walk-forward backtest framework with look-ahead-bias guards.
- Benchmark tracking vs equal-weight universe and BTC (alpha measurement).
- Anomaly flag for historically-extreme feature values (wild card list).
- Cross-coin / global features (BTC dominance trend, ETH/BTC ratio, sector strength, total mcap).
- Regime detector (BTC trend + funding + global mcap voting).
- Reusable thresholds skill for alert routing.

### Non-Goals (explicit, Phase 1 will not do)
- Real trading execution / broker integration (signals only; no orders).
- Mobile app.
- Multi-user / SaaS deployment.
- Web dashboard or UI (deferred to v0.4).
- Spot universe (perp-only).
- Sub-15-minute timeframes.
- Custom indicator builder UI.
- Sentiment beyond NewsAPI + RSS + LunarCrush + LLM-judge bulk RSS (no Twitter/Reddit deep scraping).
- Cross-exchange (OKX only).
- Survivorship-bias-free backtest (delisted coins NOT included; ~3–5% optimism accepted).
- Classical ML model (deferred to v0.3).
- 4h or 7d prediction horizons (deferred to v0.2 / v0.4).

### Deferred (planned, but post Phase 1)
- v0.2: 4h horizon, sector concentration overlay, notification prefs v2.
- v0.3: Classical ML (LightGBM) as ensemble or replacement, A/B harness activation, drift monitor automation.
- v0.4: 7d horizon, web dashboard.

---

## 3. Background

Koray is an active crypto trader/researcher in Turkey. Current daily routine:
- Runs deep-scans across ~287 OKX TR universe (saved to `C:\Users\Koray\Desktop\crypto-scans\`).
- Operates crypto-intel-hub (custom plugin, Phase 1 v0.1.0): watchlist price tracker, sentiment analyst, signal generator (formula `0.3·momentum + 0.3·sentiment + 0.2·volume_anomaly + 0.2·technical`), Telegram alerts, markdown reports, scheduler.
- Uses crypto-trading-desk plugin (hugoguerrap/crypto-claude-desk v1.0.0) with seven MCP servers: advanced_indicators, exchange_ccxt_ultra, futures_data, learning_db (predictions/patterns/trades schema in SQLite), market_microstructure, technical_analysis, ultra_simple.

The motivation for crypto-predictor: the existing signal-generator in intel-hub is a coarse weighted formula on a watchlist of ~5 coins. It does not give probabilities (only raw scores), does not validate outcomes, and does not scan the broader universe. crypto-predictor is the natural evolution — universe-wide, probability-based, with self-measurement.

Key constraint that shapes the entire design: with ~340 coins to score daily, the prediction approach cannot afford to call an LLM per coin (cost and latency). Math must be vectorized; LLM is used only to write short reasoning summaries on the top-40 candidates.

---

## 4. Vision

> **crypto-predictor** scans the OKX-Global perpetual universe every morning, produces calibrated direction probabilities and expected returns for every coin, ranks the top long and short candidates, and tracks its own accuracy over time so it can recognize when its assumptions stop working and recalibrate.

---

## 5. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    crypto-predictor (new plugin)                     │
│                                                                       │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────────┐    │
│  │  Scheduler  │───▶│ Feature ETL  │───▶│ Heuristic Scorer     │    │
│  │ (06:00 UTC) │    │ (cache layer)│    │ (direction + magnitude)│  │
│  └─────────────┘    └──────────────┘    └──────────┬───────────┘    │
│                              ▲                      │                 │
│                              │                      ▼                 │
│  ┌──────────────────┐  ┌──────────┐    ┌──────────────────────┐    │
│  │ Validator        │  │ Cache DB │    │ Probability Calibrator│    │
│  │ (24h later check)│  │(features)│    │ (isotonic, per-regime)│    │
│  └────────┬─────────┘  └──────────┘    └──────────┬───────────┘    │
│           │                                        │                 │
│           ▼                                        ▼                 │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  predictions.db (SQLite, own schema)                          │  │
│  └──────────────────────────────────────────────────────────────┘  │
│           │                                        │                 │
│           ▼                                        ▼                 │
│  ┌──────────────────┐                  ┌──────────────────────┐    │
│  │ Metrics & Report │◀─────────────────│  Ranker + Markdown   │    │
│  │  (hit, MAE,alpha)│                  │  Renderer + Telegram │    │
│  └──────────────────┘                  └──────────────────────┘    │
└──────────────────────────────────────────┬──────────────────────────┘
                                            │
        ┌───────────────────────────────────┼───────────────────────────┐
        │              consumes (read-only) │                            │
        ▼                                   ▼                            ▼
┌────────────────────┐         ┌────────────────────────┐    ┌─────────────────┐
│ trading-desk MCPs  │         │ intel-hub MCPs         │    │ Telegram Bot    │
│ • exchange (OHLCV) │         │ • crypto-news (sent.)  │    │ (reused)        │
│ • futures          │         │ • crypto-onchain (opt.)│    │                 │
│ • technical        │         │ • crypto-whale (opt.)  │    │                 │
│ • microstructure   │         └────────────────────────┘    └─────────────────┘
│ • adv. indicators  │
└────────────────────┘
```

### 5.1 Component Inventory

| Component | Type | Responsibility |
|---|---|---|
| `mcp-servers/crypto-predictor/` | Python MCP server (FastMCP) | Core MCP tools: `rank_universe`, `predict_coin`, `validate_pending`, `get_track_record`, `get_calibration_curve`, `run_backtest`, `recalibrate`, `health_check` |
| `predictions.db` | SQLite | Own `predictions`, `predictions_features`, `metrics_rolling`, `patterns`, `calibration_maps`, `regime_log` tables |
| `features.db` | SQLite | Feature snapshot cache (coin × timestamp × feature_name × value) |
| `data/history/` | Parquet partitioned by symbol | Bulk-ingested OHLCV + funding + OI + L/S + liquidation history (6 months) |
| `agents/predictor.md` | Claude agent persona | Generates per-coin reasoning summary (LLM, Haiku) |
| `agents/ranker.md` | Claude agent persona | Top-K selection + composite scoring narrative |
| `agents/validator.md` | Claude agent persona | Drives validation runs + drift detection |
| `skills/predict-format/` | Skill | Markdown report template + Telegram summary template |
| `skills/predict-thresholds/` | Skill | Alert routing rules + thresholds config |
| `commands/predict-scan.md` | Slash command | Full daily run (universe → predict → rank → report → telegram) |
| `commands/predict-coin.md` | Slash command | Single coin on-demand prediction |
| `commands/predict-track.md` | Slash command | Track record dashboard (text format) |
| `commands/predict-validate.md` | Slash command | Manually validate pending predictions (scheduler fallback) |
| `commands/predict-backtest.md` | Slash command | Run walk-forward backtest |
| `scheduler/` | APScheduler service | 06:00 UTC daily run, 06:30 UTC validation, weekly metrics, monthly recalibrate |
| `backtest/` | Python module | Walk-forward orchestrator, calibration trainer, metrics computer |
| `scripts/ingest_history.py` | One-shot script | Bulk historical data ingest into parquet (run once at setup) |
| `tests/` | Pytest | Unit + integration + golden data tests |

### 5.2 Daily Data Flow (06:00 UTC example)

1. **Trigger** (06:00 UTC): Scheduler fires `predict-scan` job.
2. **Feature ETL** (~3–5 min): For 340 perps, parallel batches fetch OHLCV (15m / 1h / 4h / 1d), funding rate, OI, long/short ratio, taker buy/sell, top-3 sentiment scores, microstructure imbalance. Z-score normalize against rolling 90-day history. Write to `features.db`.
3. **Scoring** (~30 s): Vectorized heuristic formula applied. Per-coin raw direction score (−1..+1) + raw magnitude (% expected). Apply per-regime isotonic calibration mapping → P(↑), P(↓). Composite score = `max(P(↑), P(↓)) × |expected_return|`.
4. **Anomaly check** (~5 s): For each coin, flag wild-card if any critical feature |z-score| > 3.
5. **Ranking + LLM summary** (~1–2 min): Top 20 long + top 20 short selected. For each, Claude Haiku writes 2–3 sentence "why on the list" summary grounded in top-3 feature values.
6. **Output** (~10 s): Markdown report written to `C:\Users\Koray\Desktop\crypto-scans\predict-YYYY-MM-DD-HHMM.md`. Top-5 long + top-5 short summary pushed to Telegram. Wild-card and high-conviction alerts pushed as separate short messages.
7. **State persist**: 340 prediction rows inserted into `predictions.db` with status='pending', regime tag, calibration_map_version, formula_version.

**Cadence summary**:
- 06:00 UTC daily — predict-scan
- 06:30 UTC daily — validate-pending (24h-old predictions)
- Sunday 07:00 UTC — weekly-metrics report
- Monthly 1st 07:00 UTC — recalibrate

---

## 6. Data Sources and Sentiment Strategy

### 6.1 Numeric data (OKX)
- **OHLCV**: via crypto-exchange MCP (`fetch_ohlcv_data`, `fetch_multiple_timeframes`). Rate limit ~10 req/sec; batched 5-coin chunks with backoff.
- **Funding rate, OI, L/S ratio, taker buy/sell, liquidations**: via crypto-futures MCP.
- **Technical indicators (RSI, MACD, BB, ADX, MA)**: via crypto-technical + crypto-advanced-indicators MCPs.
- **Microstructure (spread, depth, imbalance)**: via crypto-market-microstructure MCP.
- **Global stats (BTC dominance, total mcap, sector indices)**: via crypto-data MCP (`get_dominance_stats`, `get_market_trends`, `get_crypto_categories`).

### 6.2 Sentiment data (tiered hybrid B + C)

Sentiment coverage across all 340 coins is achieved with a tiered strategy:

| Tier | Coin count | Source | Frequency |
|---|---|---|---|
| **Tier 1: top 100 mcap** | ~100 | NewsAPI + RSS (CoinDesk, Cointelegraph, Decrypt) — per-coin search | Daily |
| **Tier 2: rank 100–200** | ~100 | LunarCrush Lite plan (~$24/month, 100 coins) social score | Daily |
| **Tier 3: rank 200–340** | ~140 | LLM-judge bulk RSS: fetch all crypto RSS once, Claude Haiku classifies each article by `coins_mentioned[]` + sentiment(-1..+1), bucket per coin | Daily |
| **Fallback for any tier with no data** | — | Price-action proxy: 7-day rolling return + volatility | — |

The composite `news_sent_24h` feature is computed identically per coin regardless of tier source. The `mcap_rank_weight(coin)` function (1.0 for top 100, 0.7 for 100–200, 0.4 for 200–340) attenuates sentiment weight in the heuristic formula for less-reliable tiers.

### 6.3 LLM usage budget (Phase 1)

| Use case | Frequency | Volume | Est. monthly cost |
|---|---|---|---|
| Bulk RSS judge (Tier 3 sentiment) | Daily | ~50 articles × Haiku | ~$15 |
| Per-candidate reasoning summary | Daily | 40 candidates × Haiku | ~$6 |
| Pattern recognition (weekly) | Weekly | ~10 calls × Sonnet | ~$3 |
| **Total estimated** | | | **~$24/month** |

Combined with LunarCrush Lite (~$24): **~$48/month total external cost**. Hard cap config: $75/month, exceeds → alert + fallback to free sources.

---

## 7. Feature Pipeline (6 Families, ~30 features)

All features are computed per coin per run, then **z-score normalized** against rolling 90-day distribution before entering the formula, so coins are comparable.

### 7.1 Family 1 — Momentum (direction hint)

| Feature | Computation | Window |
|---|---|---|
| `ret_15m_z` | log-return 15m, z-score | 90d 15m bars |
| `ret_1h_z` | log-return 1h, z-score | 90d 1h bars |
| `ret_4h_z` | log-return 4h, z-score | 90d 4h bars |
| `ret_24h_z` | log-return 24h, z-score | 90d 1d bars |
| `ret_7d_z` | log-return 7d, z-score | 90d 1d bars |
| `mom_consistency` | count(sign(bar_return) > 0) / 24 over last 24×1h | 1h bars |

### 7.2 Family 2 — Perp microstructure (most discriminating)

| Feature | Computation | Source |
|---|---|---|
| `funding_z` | funding rate, 30d z-score | crypto-futures |
| `funding_extreme` | binary: |funding_z| > 2 | derived |
| `oi_growth_24h` | (OI_now / OI_24h_ago) − 1 | crypto-futures |
| `oi_growth_z` | yukarıdaki, z-score | derived |
| `ls_ratio` | long/short account ratio | crypto-futures |
| `ls_ratio_change_4h` | last-4h change | derived |
| `taker_buy_sell_1h` | taker buy USDT / total taker USDT | crypto-futures |
| `liq_pressure_long_4h` | summed long liquidation USDT, last 4h | crypto-futures |
| `liq_pressure_short_4h` | summed short liquidation USDT, last 4h | crypto-futures |

### 7.3 Family 3 — Volume / liquidity (confidence multiplier)

| Feature | Computation |
|---|---|
| `vol_z_24h` | 24h USDT volume, z-score vs 30d |
| `vol_vs_mcap_rank` | volume / mcap, percentile rank |
| `spread_bps` | bid-ask spread (basis points) |
| `depth_1pct` | USDT depth at 1% from mid (both sides) |

### 7.4 Family 4 — Technical (classical triggers)

| Feature | Computation | Source |
|---|---|---|
| `rsi_14_1h` | RSI(14) on 1h close | crypto-technical |
| `rsi_overbought` | binary: RSI > 70 | derived |
| `rsi_oversold` | binary: RSI < 30 | derived |
| `macd_hist_1h` | MACD histogram on 1h | crypto-technical |
| `bb_position_1h` | (price − lower_bb) / (upper_bb − lower_bb) | crypto-technical |
| `adx_14_1h` | ADX trend strength | crypto-advanced-indicators |
| `price_vs_sma50` | (price / SMA50) − 1 | derived |

### 7.5 Family 5 — Sentiment (psychology)

| Feature | Computation |
|---|---|
| `news_sent_24h` | NewsAPI + RSS + LunarCrush + LLM-judge composite, last 24h |
| `social_sent_24h` | LunarCrush social score (Tier 1–2) or LLM-judge social bucket (Tier 3) |
| `sent_velocity` | sent_24h − sent_7d_avg (acceleration) |
| `news_volume_z` | article count, z-score (attention grabbing) |

### 7.6 Family 6 — Cross-coin / global (context)

| Feature | Computation |
|---|---|
| `btc_dom_trend_7d` | BTC dominance 7d slope |
| `eth_btc_trend_7d` | ETH/BTC ratio 7d slope |
| `total_mcap_z` | total mcap z-score |
| `sector_strength_24h` | the coin's sector index 24h return (from crypto-categories) |
| `coin_btc_corr_30d` | 30d Pearson correlation with BTC |

---

## 8. Heuristic Model

### 8.1 Direction tilt formula (raw, −1..+1)

```
direction_raw =  0.20 × tilt_momentum
              +  0.25 × tilt_perp_microstructure
              +  0.10 × tilt_volume
              +  0.15 × tilt_technical
              +  0.15 × tilt_sentiment × mcap_rank_weight(coin)
              +  0.15 × tilt_global × (1 − coin_btc_corr_30d)
```

Weight rationale:
- **0.25 perp microstructure**: funding + OI + L/S + liquidations are the most ex-ante information-rich for 24h moves in perp markets (positioning extremes mean-revert).
- **0.20 momentum**: persistent but susceptible to whipsaw; second-highest.
- **0.15 sentiment × mcap_rank_weight**: meaningful for top 100 (weight = 1.0), attenuated for smaller caps where signal is noisy.
- **0.15 global × (1 − coin_btc_corr_30d)**: BTC-tilted coins inherit BTC trend strongly; uncorrelated coins discount global signal.
- **0.15 technical**: well-understood baseline, no surprises.
- **0.10 volume**: confidence multiplier rather than direction, but volume z-scores correlate weakly with direction.

### 8.2 Example tilt function (perp microstructure)

```python
def tilt_perp(features):
    # Negative funding → shorts paying → long-bias tilt (mean-reversion of crowded shorts)
    funding_tilt = -clip(features.funding_z / 2, -1, 1)

    # OI rising + price rising = real long pressure; OI rising + price falling = trapped longs
    oi_confirm = sign(features.ret_4h_z) * clip(features.oi_growth_z, -1, 1)

    # Short liquidation cascades create short-squeeze upward pressure
    liq_total = features.liq_pressure_short_4h + features.liq_pressure_long_4h + 1
    liq_tilt = clip(
        (features.liq_pressure_short_4h - features.liq_pressure_long_4h) / liq_total,
        -1, 1
    )

    return 0.4 * funding_tilt + 0.3 * oi_confirm + 0.3 * liq_tilt
```

Other tilt functions (`tilt_momentum`, `tilt_volume`, `tilt_technical`, `tilt_sentiment`, `tilt_global`) follow the same pattern: clip z-scores, combine with hand-tuned sub-weights, return value in [−1, +1].

### 8.3 Magnitude estimator

```
base_vol_24h = realized_volatility(coin, window=30d) × sqrt(1)   # 1-day horizon
strength = abs(direction_raw)
regime_mult = {BULL: 1.15, BEAR: 0.90, CHOP: 1.00}[current_regime]

expected_return = base_vol_24h × (0.5 + 0.5 × strength) × regime_mult × sign(direction_raw)
```

Interpretation: if signal is strong (|raw|=1), expected magnitude = full 30d realized vol; if weak (|raw|=0), expected magnitude = half. BULL regime expands long magnitudes; BEAR contracts.

### 8.4 Mcap rank weight

```python
def mcap_rank_weight(coin):
    rank = current_mcap_rank(coin)  # cached weekly
    if rank <= 100:   return 1.0
    if rank <= 200:   return 0.7
    return 0.4
```

---

## 9. Regime Detection

Daily regime computed from BTC trend + funding + global mcap voting:

```python
def detect_regime():
    btc_30d_return = price(BTC, today) / price(BTC, today - 30d) - 1
    btc_funding_avg_7d = mean(funding_rate(BTC, last_7d))
    global_mcap_trend = sign(total_mcap_30d_slope)

    bull_votes = (
        (btc_30d_return > 0.05) +
        (btc_funding_avg_7d > 0) +
        (global_mcap_trend > 0)
    )
    bear_votes = (
        (btc_30d_return < -0.05) +
        (btc_funding_avg_7d < -0.0001) +
        (global_mcap_trend < 0)
    )

    if bull_votes >= 2: return "BULL"
    if bear_votes >= 2: return "BEAR"
    return "CHOP"
```

The regime is stored per-day in `regime_log` and tagged on every prediction (used in calibration and per-regime metric breakdowns).

---

## 10. Calibration

### 10.1 Methodology — per-regime isotonic regression

Raw direction scores do not equal probabilities. Calibration maps `raw_direction_score` → `P(↑)` empirically.

Training procedure (per regime):
1. Collect (raw_score, actual_label) pairs from backtest period: label = 1 if 24h return > 0, else 0.
2. Bucket raw scores into 10 quantile bins.
3. For each bin, compute empirical P(label=1) within the bin.
4. Fit `sklearn.isotonic.IsotonicRegression(increasing=True, out_of_bounds='clip')` on (raw_score, label) — this guarantees monotonic, smooth mapping.
5. Save fitted mapping to `calibration_maps` table, versioned by date and regime.

At inference:
```python
P_up = calibration_maps[current_regime].predict([direction_raw])[0]
P_down = 1 - P_up
```

### 10.2 Calibration quality acceptance

Calibration is considered acceptable if the average absolute deviation between bucket predicted-P and bucket empirical-P is ≤ 5% on the validation holdout. Otherwise, weight tuning required.

### 10.3 Recalibration triggers

| Trigger | Action |
|---|---|
| Monthly schedule (1st of month, 07:00 UTC) | Refit on rolling last 3 months (live + initial backtest) |
| Drift detection: rolling 7d Brier > backtest Brier + 0.05 | Telegram alert + auto-trigger recalibration |
| Manual: `predict-coin recalibrate --reason "..."` | One-off, requires reason argument |

Old calibration maps are kept in `calibration_maps` table (versioned), so old predictions remain interpretable.

---

## 11. Anomaly Detection (Wild Cards)

After prediction is computed, an additional layer flags coins whose feature space is historically extreme:

```python
CRITICAL_FEATURES = [
    "funding_z", "oi_growth_z", "vol_z_24h",
    "sent_velocity", "liq_pressure_long_4h", "liq_pressure_short_4h"
]

anomalous = any(abs(features[name]) > 3.0 for name in CRITICAL_FEATURES)
if anomalous:
    prediction.confidence_flag = "WILD_CARD"
    prediction.composite_score *= 0.7   # demote in ranking
```

Wild-card coins are **excluded from the main top-K long and short lists**. They appear in a separate **Wild Cards** section of the report. This prevents historically-unprecedented setups from polluting the ranked outputs while still surfacing them for human attention.

Telegram delivers wild cards as a separate short message: `🃏 Wild: AGIX (OI ekstrem), WIF (funding ekstrem)`.

---

## 12. Backtest Framework

### 12.1 Walk-forward methodology

The backtest window is divided into three rolling slices:

```
[──── training (3 months) ────][── calibration (1 month) ──][─ validation (1 month) ─]
                                  ↑                          ↑
                                  fit isotonic                report metrics
                                  raw → P_empirical
```

The window slides forward every 7 days. For each iteration, the calibration is fit on the calibration slice and metrics are computed on the validation slice. Walk-forward prevents over-fitting and approximates realistic deployment.

### 12.2 Look-ahead bias guard

For any prediction at date D, only data available before `D 00:00:00 UTC` is used. Enforced at the data-fetch layer:

```python
class FeatureFetcher:
    def __init__(self, asof: datetime):
        self.asof = asof   # any query with timestamp >= asof raises

    def fetch_ohlcv(self, symbol, timeframe, lookback_bars):
        bars = read_parquet(symbol, timeframe)
        bars = bars[bars.timestamp < self.asof]   # strict less-than
        return bars.tail(lookback_bars)
```

A dedicated unit test verifies that any attempt to read data with `timestamp >= asof` raises an error (look-ahead-guard test).

### 12.3 Backtest output metrics

| Metric | Target |
|---|---|
| Direction hit rate (overall) | > 58% |
| Direction hit rate per regime | > 55% in each regime |
| Magnitude MAE | < naive volatility forecast MAE |
| Brier score | < 0.23 |
| Calibration MAE (5 bucket avg) | ≤ 5% |
| Top-20 long alpha vs equal-weight | > +1.5% per 24h |
| Top-20 short alpha vs equal-weight | > +1.0% per 24h |
| Wild-card hit rate | < overall hit rate (anomaly flag is doing its job) |

### 12.4 Backtest data source

The bulk-ingest script (`scripts/ingest_history.py`) runs **once at setup**: fetches 6 months of OHLCV (4 timeframes × 340 perps), funding rate, OI, L/S, liquidation history from OKX via crypto-exchange / crypto-futures MCPs. Stores as Parquet in `data/history/<symbol>/<timeframe>.parquet`. Ingest takes ~6 hours wall time due to rate limits; the script is idempotent and resumable.

Production runs do not re-ingest; they pull the rolling last-90-days into memory at startup, lazy-load older windows from Parquet for backtest only.

**Survivorship bias acknowledgement**: bulk-ingest only fetches coins listed *today* on OKX Global perp. Coins that delisted during the 6-month window are excluded. This biases backtest metrics +3–5% in our favour vs. live deployment. We accept this limitation in Phase 1; every backtest report carries an explicit `survivorship_bias: present` flag in its header.

### 12.5 Backtest command

```bash
claude /predict-backtest --start 2026-01-01 --end 2026-05-31 --output backtest-report.md
```

Or interactively with custom weights:

```bash
claude /predict-backtest --start 2026-01-01 --end 2026-05-31 \
  --weights "momentum=0.18,perp=0.27,volume=0.10,technical=0.15,sentiment=0.15,global=0.15" \
  --output backtest-tuned.md
```

Produces `backtest-report.md` plus saved `calibration_map.json` (regime-keyed) and `formula_weights.json`. Production loads these artifacts on startup.

---

## 13. B Loop — Validation and Learning

### 13.1 Schedule

| Cron | Job | Window |
|---|---|---|
| Daily 06:00 UTC | `predict-scan` | Generate today's predictions |
| Daily 06:30 UTC | `validate-pending` | Resolve yesterday's pending predictions |
| Sunday 07:00 UTC | `weekly-metrics` | Generate `metrics-weekly-YYYY-Www.md` |
| Monthly 1st 07:00 UTC | `recalibrate` | Refit calibration maps on rolling 3-month data |

### 13.2 `validate-pending` job

```python
def validate_pending():
    pending = db.query("""
        SELECT * FROM predictions
        WHERE status = 'pending'
          AND julianday('now') - julianday(created_at) >= 1.0
    """)

    for pred in pending:
        actual_return_24h = fetch_actual_return(pred.symbol, pred.created_at, hours=24)

        direction_correct = (
            (pred.prediction == "up" and actual_return_24h > 0) or
            (pred.prediction == "down" and actual_return_24h < 0)
        )

        magnitude_error = abs(pred.target_value - actual_return_24h)
        magnitude_close = magnitude_error < 0.5 * abs(pred.target_value)

        db.update(pred.id, {
            "status": "correct" if direction_correct else "incorrect",
            "actual_outcome": actual_return_24h,
            "error_margin": magnitude_error,
            "validated_at": now_iso(),
            "evaluation": f"dir={'OK' if direction_correct else 'FAIL'}, "
                          f"mag_close={'OK' if magnitude_close else 'FAIL'}",
        })

    update_rolling_metrics()
    detect_calibration_drift()
```

### 13.3 Rolling metrics

Maintained continuously, queryable via `/predict-track`:

```sql
CREATE TABLE metrics_rolling (
    window         TEXT,              -- '7d', '30d', '90d'
    regime         TEXT,              -- 'BULL', 'BEAR', 'CHOP', 'ALL'
    direction      TEXT,              -- 'long', 'short', 'all'
    n_predictions  INTEGER,
    n_correct      INTEGER,
    hit_rate       REAL,
    mae            REAL,
    brier          REAL,
    topk_alpha     REAL,              -- vs equal-weight universe
    topk_alpha_btc REAL,              -- vs BTC hold
    updated_at     TEXT,
    PRIMARY KEY (window, regime, direction)
);
```

### 13.4 Pattern detector

Weekly job examines high-win-rate recent predictions and surfaces common feature combinations:

```python
def detect_patterns():
    recent_wins = db.query("SELECT * FROM predictions WHERE status='correct' AND validated_at > now-30d")
    # Cluster features that frequently co-occur in wins
    candidate_patterns = mine_frequent_feature_buckets(recent_wins, min_support=10)
    for pattern in candidate_patterns:
        win_rate = compute_pattern_win_rate(pattern, all_recent_predictions)
        recommendation = "SEEK" if win_rate > 0.65 else "AVOID" if win_rate < 0.50 else "NEUTRAL"
        upsert_pattern(pattern, win_rate, recommendation)
```

Patterns appear in the daily report's **Active Patterns** section. Reused schema from trading-desk's learning-db `patterns` table (adapted).

---

## 14. Storage Schema

All in `predictions.db` (own SQLite file, separate from trading-desk's learning.db).

```sql
-- 14.1 Predictions
CREATE TABLE predictions (
    id                  TEXT PRIMARY KEY,
    symbol              TEXT NOT NULL,
    horizon_hours       INTEGER NOT NULL DEFAULT 24,
    prediction          TEXT NOT NULL CHECK (prediction IN ('up','down')),
    p_direction         REAL NOT NULL,                 -- calibrated P(↑) for prediction='up', P(↓) for 'down'
    target_value        REAL NOT NULL,                 -- expected_return (signed %)
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
CREATE INDEX idx_pred_symbol ON predictions(symbol);
CREATE INDEX idx_pred_status ON predictions(status);
CREATE INDEX idx_pred_created ON predictions(created_at);
CREATE INDEX idx_pred_regime ON predictions(regime);

-- 14.2 Feature snapshot (per prediction)
CREATE TABLE predictions_features (
    prediction_id TEXT NOT NULL,
    feature_name  TEXT NOT NULL,
    raw_value     REAL,
    z_value       REAL,
    PRIMARY KEY (prediction_id, feature_name),
    FOREIGN KEY (prediction_id) REFERENCES predictions(id)
);

-- 14.3 Calibration maps (versioned)
CREATE TABLE calibration_maps (
    version    TEXT NOT NULL,
    regime     TEXT NOT NULL,
    map_json   TEXT NOT NULL,        -- serialized IsotonicRegression model (or sklearn pickle path)
    fit_window TEXT NOT NULL,        -- e.g. "2026-03-01..2026-05-31"
    created_at TEXT NOT NULL,
    PRIMARY KEY (version, regime)
);

-- 14.4 Regime log
CREATE TABLE regime_log (
    date              TEXT PRIMARY KEY,
    regime            TEXT NOT NULL,
    btc_30d_return    REAL,
    btc_funding_avg   REAL,
    global_mcap_trend REAL
);

-- 14.5 Rolling metrics
CREATE TABLE metrics_rolling (
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

-- 14.6 Patterns
CREATE TABLE patterns (
    name            TEXT PRIMARY KEY,
    conditions      TEXT,             -- JSON array of {feature, op, threshold}
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

-- 14.7 Run log (auditability)
CREATE TABLE runs (
    run_id           TEXT PRIMARY KEY,
    job              TEXT NOT NULL,    -- 'predict-scan', 'validate-pending', etc.
    started_at       TEXT NOT NULL,
    completed_at     TEXT,
    status           TEXT CHECK (status IN ('ok','error','partial')),
    n_predictions    INTEGER,
    n_errors         INTEGER,
    error_summary    TEXT,
    formula_version  TEXT,
    calibration_version TEXT
);
```

`features.db` mirrors a wide table for cache:

```sql
CREATE TABLE feature_snapshot (
    symbol       TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    value        REAL,
    PRIMARY KEY (symbol, timestamp, feature_name)
);
CREATE INDEX idx_fs_symbol_ts ON feature_snapshot(symbol, timestamp);
```

---

## 15. Output Formats

### 15.1 Daily markdown report

Saved to `C:\Users\Koray\Desktop\crypto-scans\predict-YYYY-MM-DD-HHMM.md`:

```markdown
# Crypto Predictor — Daily Report
**2026-06-01 06:00 UTC** | Regime: **BULL** | Universe: 340 OKX Global USDT-Perp

## Summary
- Scanned: 340 coins (327 successful, 13 skipped — data freshness fail)
- Top 20 long candidates, top 20 short candidates, 4 wild cards
- Active patterns: 3 SEEK, 1 AVOID
- Rolling 30d performance: Hit 61.4% · Alpha +2.81% · Brier 0.219

## 📈 Top Long Candidates

| # | Coin    | P↑   | Exp.Ret | Composite | Top signals                                              |
|---|---------|------|---------|-----------|----------------------------------------------------------|
| 1 | SOLUSDT | 0.78 | +5.2%   | 0.406     | funding −0.04% (ext. short), OI +18% 24h, news +0.34     |
| 2 | AVAXUSDT| 0.74 | +4.8%   | 0.355     | ret_4h_z +2.1, taker buy 62%, sector strength +2.3%      |
... (20 rows)

## 📉 Top Short Candidates

| # | Coin    | P↓   | Exp.Ret | Composite | Top signals                                              |
|---|---------|------|---------|-----------|----------------------------------------------------------|
| 1 | ENSUSDT | 0.71 | −4.1%   | 0.291     | funding +0.06% (ext. long), liq cascade 3 events 4h      |
... (20 rows)

## ⚡ High Conviction (P > 0.78 AND |Exp.Ret| > 4%)
- **SOLUSDT +5.2% (P 0.78)** — funding extreme negative, short squeeze setup
- **AVAXUSDT +4.8% (P 0.74)** — momentum + sector tailwind aligned

## 🃏 Wild Cards (anomaly detected, handle with caution)
- **AGIXUSDT**: OI grew +340% in 4h, historically unprecedented. Direction P↑ 0.81 but low confidence.
- **WIFUSDT**: funding +0.21% (4σ above). Extreme long crowding, either squeeze or crash.

## 🎯 Active Patterns (last 30d)
- ✅ SEEK: `funding_extreme=True + regime=BULL + oi_growth_z>1.5` → 11 occurrences, 73% win
- ✅ SEEK: `RSI<25 + sent_velocity>0.3` → 7 occurrences, 71% win
- ⚠ AVOID: `funding_z>2 + ret_24h>10%` → 9 occurrences, 22% win (overcrowded longs)

## 📊 Validation Track Record (Rolling Windows)

| Window | Hit Rate | n     | MAE   | Brier | Top-K Alpha vs Universe |
|--------|----------|-------|-------|-------|-------------------------|
| 7d     | 64.1%    | 280   | 2.18% | 0.205 | +3.12%                  |
| 30d    | 61.4%    | 1,200 | 2.34% | 0.219 | +2.81%                  |
| 90d    | 60.2%    | 3,650 | 2.41% | 0.224 | +2.45%                  |

## 📉 Skipped Coins
- AKROUSDT: last OHLCV bar 12 min stale
- ... (12 more)

---
*Generated by crypto-predictor v0.1.0 · formula_v3 · calibration 2026-05-01*
*Not financial advice. Backtest assumes no slippage.*
```

### 15.2 Telegram daily summary (compact, ~600 chars)

```
🔮 Predictor 2026-06-01 06:00 UTC | BULL

📈 Top 5 Long:
1. SOL  P↑0.78 → +5.2%
2. AVAX P↑0.74 → +4.8%
3. LINK P↑0.73 → +4.1%
4. INJ  P↑0.71 → +3.9%
5. ARB  P↑0.69 → +3.5%

📉 Top 5 Short:
1. ENS  P↓0.71 → −4.1%
2. NEAR P↓0.69 → −3.8%
3. ATOM P↓0.66 → −3.2%
4. AAVE P↓0.65 → −3.1%
5. CRV  P↓0.64 → −2.9%

30d hit 61.4% · Alpha +2.81%
📄 reports/predict-2026-06-01-0600.md
```

### 15.3 Telegram alert routing

| Alert type | Trigger | Frequency cap |
|---|---|---|
| Daily summary | Every 06:05 UTC | 1/day always |
| High conviction | P > 0.78 AND |Exp.Ret| > 4% | Expected ~5–10 candidates/day, **batched into one combined message** (one bullet per candidate) |
| Wild card | Anomaly flag fired | 1 combined message/day, only if non-empty |
| Calibration drift | Rolling 7d Brier > backtest Brier + 0.05 | 1 message, no repeat for 24h |
| Pattern transition | SEEK → AVOID | 1 message per transition |
| Health failure | No daily report by 06:15 UTC | 1 message + ping fallback |

Maximum daily Telegram messages: ~5 (no spam).

### 15.4 `/predict-track` view (CLI / markdown)

```
Crypto Predictor Track Record
=============================
Window: 30d | Regime: ALL

Direction Hit Rate:     61.4%  (n=1,200, 736 correct)
  Long predictions:     63.8%  (n=600, 383 correct)
  Short predictions:    58.9%  (n=600, 353 correct)

Per Regime:
  BULL  64.7%  (n=290)
  BEAR  57.8%  (n=420)
  CHOP  61.1%  (n=490)

Magnitude:
  MAE                   2.34%
  Direction correct +   2.18%
  Direction wrong   +   2.51%

Brier Score:            0.219  (target < 0.23 ✓)

Top-K Alpha (vs benchmarks):
  vs Equal-weight     +2.81%  per 24h
  vs BTC hold         +1.24%  per 24h

Calibration (30d):
  P=0.5 bucket  ██████████ (actual 51%)  ✓
  P=0.6 bucket  ████████████ (actual 59%) ✓
  P=0.7 bucket  ██████████████ (actual 67%) ⚠ 3% off
  P=0.8 bucket  ████████████████ (actual 74%) ⚠ 6% off
  P=0.9 bucket  █████████████████ (actual 82%) ✗ 8% off (overconfidence)

Calibration MAE (avg): 4.8% ✓ (target ≤ 5%)
Active formula version: v3 (since 2026-05-15)
Active calibration version: 2026-05-01
```

### 15.5 Benchmark tracker (alpha measurement)

Each validation cycle:

```
top_k_long_return_24h  = mean(actual_return_24h for c in top_k_long_list)
equal_weight_return_24h = mean(actual_return_24h for c in entire_universe)
btc_return_24h          = actual_return_24h for BTC

alpha_vs_universe = top_k_long_return_24h − equal_weight_return_24h
alpha_vs_btc      = top_k_long_return_24h − btc_return_24h
```

Weekly metrics report shows all three alphas and flags negative streaks (≥7 days negative alpha → manual review prompt).

---

## 16. Phasing

### Phase 1 — MVP (10 weeks, +flex on week 6)

| Week | Deliverable | Acceptance |
|---|---|---|
| 1 | Plugin scaffold (mcp-servers/, schema, scheduler skeleton, uv env) | `crypto-predictor ping` works; DBs initialize |
| 2 | Bulk-ingest script: 340 perps × 6 mo × 4 TF + futures data → parquet | `data/history/` populated; one-shot 6h run |
| 3 | Feature pipeline (6 families, z-score, caching) | `compute_features("BTCUSDT", asof=now)` returns ~30 values; unit tests pass |
| 4 | Heuristic + magnitude + regime + anomaly | `compute_raw_direction()` per coin <50ms; all tilt fns unit-tested |
| 5 | Backtest framework (walk-forward + isotonic per regime) | `/predict-backtest` produces report.md + calibration_map.json |
| 6 | Run backtest, tune weights, validate calibration | Hit rate > 58%, calibration MAE ≤ 5%; extend if needed |
| 7 | Daily orchestrator + LLM summary + ranker | `/predict-scan` 5–7min runtime; 340 prediction rows written |
| 8 | Output formatters + thresholds skill + Telegram | Sample report matches §15.1; Telegram alerts arrive |
| 9 | Validator + rolling metrics + pattern detector + benchmark | 24h post-prediction validates; `/predict-track` populated |
| 10 | E2E tests + scheduler hardening + 7-day shadow mode + go-live | No crashes in shadow; alert routing enabled |

### Roadmap beyond Phase 1

| Version | Adds | Precondition |
|---|---|---|
| v0.2 | 4h horizon, sector concentration overlay, notification prefs v2 | 30-day live Phase 1 hit rate > 58% |
| v0.3 | LightGBM ML model (ensemble or replacement), A/B harness, automated drift monitor | 60+ days live, 50K+ predictions accumulated |
| v0.4 | 7d horizon, web dashboard | If demand |

---

## 17. Testing Strategy

### 17.1 Unit tests (~80 target)

| Module | Tests |
|---|---|
| Tilt functions (6 families × ~3 cases) | 18 |
| Z-score normalize edge cases | 8 |
| Magnitude formula, regime multiplier | 6 |
| Regime detector | 6 |
| Calibration mapping, monotonic, edge bins | 8 |
| Anomaly flag thresholds | 4 |
| Composite scoring, ranking, ties | 6 |
| Validator state transitions | 6 |
| Output formatters (markdown schema, Telegram <800 chars) | 8 |
| Thresholds skill, alert routing | 6 |
| Backtest orchestrator, walk-forward window | 4 |
| Look-ahead-bias guard (`FeatureFetcher(asof=D)`) | 2 |

### 17.2 Integration tests

`tests/integration/test_e2e_synthetic.py`:
- 10 fake coins with deterministic OHLCV/funding/sentiment.
- Full pipeline: feature → score → calibrate → rank → output → validate.
- Output snapshot assertion.
- Runtime < 30 seconds.

### 17.3 Backtest as mega integration test

The 6-month backtest exercises every component except output formatters and Telegram delivery. If hit rate > 58% and calibration MAE ≤ 5% on holdout, Phase 1 quality bar is met.

### 17.4 Golden data tests

`tests/golden/` stores input snapshots and expected output snapshots. Any change to a tilt function or feature definition must update goldens with explicit human review (regression detector).

### 17.5 Shadow mode (Week 10)

- 7 days running in production with alerts **disabled** (one daily health-check Telegram ping).
- User reads each morning report manually and notes any "this doesn't make sense" cases.
- Acceptance: zero crashes, hit rate > 55% on shadow week, no obvious nonsense in top-5 lists.
- Go-live = enable alert routing.

---

## 18. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Look-ahead bias in backtest | High (easy to make) | System over-claims accuracy | `FeatureFetcher(asof=D)` strict guard, dedicated unit test |
| OKX rate limit during bulk-ingest | Medium | Week 2 stretches | Exponential backoff + idempotent parquet cache + 5-coin batches |
| Coin churn (perp delisting/listing) | High | Inconsistent predictions | Fresh `get_trading_pairs()` per run, delisted-mark in cache, skip in validation |
| Sentiment scarcity for small caps | High | Weak signal in tier 3 | `mcap_rank_weight` attenuates; LLM-judge bulk RSS fallback |
| Calibration overfitting | Medium | "P=0.7 actually 62%" | Walk-forward, holdout, monthly recalibration |
| Regime shift mid-deployment | Medium | Old calibration miscalibrates | Regime-specific maps + drift detection + manual recalibrate command |
| LLM summary hallucination | Low | Report cites wrong feature values | Wire feature values into prompt, template-validate output via regex; fallback to "no summary" |
| Budget overrun (LunarCrush + LLM) | Low | $50+/month | Monthly cap config, call counter, fallback to free sources |
| Scheduler death (laptop sleep, crash) | High | Missing days | Health-check at 06:15 UTC; alert + manual `/predict-scan` fallback |
| Survivorship bias | Certain | +3–5% optimism vs reality | Flag explicitly in every backtest report; accept limitation |
| Magnitude sign error | Medium | "Up +5%" turns out −5% | Track signed magnitude error separately; if MAE not improving, revisit formula |
| 10-week motivation loss | Medium | Project abandoned | Weekly demoable deliverable; first real report week 7 |

---

## 19. Success Criteria (Go/No-Go at Week 10)

| Metric | Threshold |
|---|---|
| Direction hit rate (rolling 30d) | ≥ 58% |
| Calibration MAE (5-bucket avg) | ≤ 5% |
| Top-K alpha vs equal-weight (30d) | ≥ +1.5% |
| Brier score | ≤ 0.23 |
| Daily run uptime | ≥ 95% (28/30 days) |
| Unit test coverage | ≥ 75% |

**Decision rule**:
- ≥4 metrics fail → halt v0.2, revise formula (regime weights, feature selection, magnitude calibration).
- 2–3 fail → advance to v0.2 but track Phase 1.5 fixes first.
- 0–1 fail → green light v0.2.

---

## 20. Open Decisions (resolved during writing-plans)

These are intentionally left for the implementation-plan phase:

- Exact Python dependency versions (`uv pin`).
- Final folder layout (will mirror crypto-intel-hub conventions).
- Test fixture data (synthetic OHLCV generator design).
- Schema migration strategy (if `predictions.db` evolves).
- Structured logging configuration (JSON, levels, rotation).
- Secrets management (`secrets.env` pattern from crypto-intel-hub reused).

---

## 21. References

- crypto-intel-hub design spec: `C:\Users\Koray\Desktop\crypto-intel-hub-design\2026-05-11-crypto-intel-hub-design.md`
- crypto-intel-hub Phase 1 plan: `C:\Users\Koray\Desktop\crypto-intel-hub-design\plans\2026-05-11-crypto-intel-hub-phase1.md`
- crypto-intel-hub source: `~/.claude/plugins/crypto-intel-hub/`
- crypto-trading-desk source: `~/.claude/plugins/cache/hugoguerrap/crypto-trading-desk/1.0.0/`
- crypto-trading-desk learning-db schema (predictions, patterns, trades): `mcp-servers/crypto_learning_db.py`
- Daily deep-scan output convention: `C:\Users\Koray\Desktop\crypto-scans\`

---

*End of design specification. Next step: writing-plans skill produces implementation plan.*
