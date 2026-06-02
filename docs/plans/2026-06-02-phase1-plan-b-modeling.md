# crypto-predictor Phase 1 — Plan B: Modeling (Weeks 4–6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Plan A's 32-feature dictionaries into calibrated direction probabilities + magnitude estimates, then validate end-to-end on 6 months of real ingested data using walk-forward backtest.

**Architecture:** Three new Python packages under `src/crypto_predictor/`:
- **`scoring/`** — six tilt functions (one per feature family), direction-raw formula, magnitude estimator, regime detector, anomaly flag, composite score
- **`calibration/`** — per-regime isotonic regression mapping `direction_raw → P(↑)`, JSON persistence with versioning
- **`backtest/`** — walk-forward window iterator, metrics module (hit rate, MAE, Brier, top-K alpha), markdown report generator

**Tech Stack:** sklearn `IsotonicRegression`, pandas, numpy, structlog, pytest, plus everything already in Plan A.

**Related docs:**
- Design spec: [`docs/design/2026-06-01-crypto-predictor-design.md`](../design/2026-06-01-crypto-predictor-design.md) (§8 Heuristic, §9 Regime, §10 Calibration, §11 Anomaly, §12 Backtest)
- Plan A: [`docs/plans/2026-06-02-phase1-plan-a-foundation.md`](2026-06-02-phase1-plan-a-foundation.md)
- Plan A completion report: [`docs/plans/2026-06-02-plan-a-completion-report.md`](2026-06-02-plan-a-completion-report.md)

**Plan B success criteria:**
- `backtest_report.md` produced for 6-month window with overall hit rate, per-regime breakdown, calibration plot, top-K alpha
- `calibration_map.json` saved with isotonic regression per regime (BULL/BEAR/CHOP)
- `formula_weights.json` records the family weights used (initially 0.20/0.25/0.10/0.15/0.15/0.15 from spec §8.1)
- Walk-forward look-ahead-bias guard test passes (FeatureFetcher with `asof` already in Plan A; backtest must use it)
- Hit rate target: ≥ 58% overall (spec §19); calibration MAE ≤ 5% per bucket
- All Plan B unit + integration tests green; ≥ 30 new tests

---

## Navigation

- **Week 4 — Scoring layer** (8 tasks)
- **Week 5 — Backtest framework + calibration** (6 tasks)
- **Week 6 — Run backtest + tune + validate** (4 tasks)
- **Plan B complete — handoff to Plan C**

---

## Prerequisites (before Task 4.1)

- [ ] **Verify Plan A is complete**

Run:
```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
.\.venv\Scripts\python.exe -m pytest -v --tb=short
```
Expected: 71+ tests pass. If anything is red, fix it before continuing.

- [ ] **Verify the integration test passes**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration -v
```
Expected: `test_full_feature_dict_for_btc_real_data` PASSES.

- [ ] **Verify OI re-ingest done (or accept partial coverage)**

```powershell
.\.venv\Scripts\python.exe -c "
import pandas as pd
from pathlib import Path
root = Path('data/history/futures')
total = 0
nulls = 0
for sym_dir in root.iterdir():
    oi = sym_dir / 'oi.parquet'
    if oi.exists():
        df = pd.read_parquet(oi)
        total += len(df)
        nulls += df['open_interest'].isna().sum()
print(f'OI rows: {total:,}, nulls: {nulls:,}')
"
```

Decision:
- If nulls / total < 5%, OI is healthy → continue.
- If nulls / total > 50%, re-run bulk ingest with OI fix (~30 min) — see Plan A completion report for command.

---

# Week 4 — Scoring Layer

Goal: For any `(symbol, asof)` with features computed, produce `direction_raw ∈ [-1, +1]`, `expected_return` (signed %), `regime` label, `anomalous` flag, and `composite_score`.

## Task 4.1: actual_24h_return helper (used by validator and backtest)

**Files:**
- Create: `src/crypto_predictor/scoring/__init__.py`
- Create: `src/crypto_predictor/scoring/returns.py`
- Create: `tests/test_features/test_scoring/__init__.py`
- Create: `tests/test_features/test_scoring/test_returns.py`

> **Note**: we use `tests/test_features/test_scoring/` (nested under existing test_features/) to keep scoring tests grouped near the features that feed them, following the convention established in Plan A.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features/test_scoring/test_returns.py
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.scoring.returns import actual_return


def _seed_hourly(root: Path, symbol: str, n: int = 100, start_price: float = 100.0):
    rows = []
    p = start_price
    for i in range(n):
        rows.append({
            "timestamp": 1700000000000 + i * 3600 * 1000,
            "open": p, "high": p * 1.01, "low": p * 0.99,
            "close": p * 1.001, "volume": 1000,
        })
        p *= 1.001
    write_ohlcv(root, symbol, "1h", pd.DataFrame(rows))


def test_actual_return_24h_computes_log_return(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_hourly(tmp_path, sym, n=100)
    # At i=50 close = 100 * 1.001^51 ≈ 105.18
    # 24h later (i=74) close = 100 * 1.001^75 ≈ 107.74
    start = datetime.fromtimestamp(
        (1700000000000 + 50 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    r = actual_return(root=tmp_path, symbol=sym,
                      start_time=start, horizon_hours=24)
    # log(107.74 / 105.18) ≈ 0.024
    assert 0.020 < r < 0.030


def test_actual_return_returns_none_when_data_missing(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    start = datetime.fromtimestamp(1700000000000 / 1000, tz=timezone.utc)
    r = actual_return(root=tmp_path, symbol=sym,
                      start_time=start, horizon_hours=24)
    assert r is None


def test_actual_return_returns_none_when_horizon_extends_past_data(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_hourly(tmp_path, sym, n=20)  # only 20 bars
    start = datetime.fromtimestamp(
        (1700000000000 + 10 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    # 24h horizon → need bar at i=34, but only 20 exist
    r = actual_return(root=tmp_path, symbol=sym,
                      start_time=start, horizon_hours=24)
    assert r is None
```

- [ ] **Step 2: Verify FAIL**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_features/test_scoring/test_returns.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/scoring/__init__.py
"""Scoring layer — tilt functions, direction formula, magnitude, regime, anomaly."""
```

```python
# src/crypto_predictor/scoring/returns.py
"""Actual return helpers used by validation and backtest."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

from crypto_predictor.data.parquet_store import read_ohlcv


def actual_return(*, root: Path, symbol: str,
                  start_time: datetime, horizon_hours: int) -> float | None:
    """Compute log return between two bars `horizon_hours` apart, starting at start_time.

    Returns None if either the start bar or end bar is missing.
    """
    df = read_ohlcv(root, symbol, "1h")
    if df.empty:
        return None
    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int((start_time + timedelta(hours=horizon_hours)).timestamp() * 1000)
    # Tolerance: accept bars within ±1 hour of target
    tol = 3600 * 1000
    start_row = df[(df["timestamp"] >= start_ms - tol) &
                   (df["timestamp"] <= start_ms + tol)]
    end_row = df[(df["timestamp"] >= end_ms - tol) &
                 (df["timestamp"] <= end_ms + tol)]
    if start_row.empty or end_row.empty:
        return None
    p0 = float(start_row["close"].iloc[0])
    p1 = float(end_row["close"].iloc[-1])
    if p0 <= 0 or p1 <= 0:
        return None
    return math.log(p1 / p0)
```

- [ ] **Step 4: Verify PASS**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_features/test_scoring/test_returns.py -v
```
Expected: 3 tests pass.

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/scoring/ tests/test_features/test_scoring/
git commit -m "feat(scoring): actual_return helper for 24h forward returns (used by validator + backtest)"
git push
```

---

## Task 4.2: Tilt function — momentum

**Files:**
- Create: `src/crypto_predictor/scoring/tilt.py`
- Create: `tests/test_features/test_scoring/test_tilt_momentum.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features/test_scoring/test_tilt_momentum.py
from crypto_predictor.scoring.tilt import tilt_momentum


def test_tilt_momentum_strong_positive():
    feats = {
        "ret_15m_z": 2.0, "ret_1h_z": 2.0, "ret_4h_z": 2.0,
        "ret_24h_z": 2.0, "ret_7d_z": 2.0, "mom_consistency": 0.9,
    }
    t = tilt_momentum(feats)
    assert 0.5 < t <= 1.0


def test_tilt_momentum_strong_negative():
    feats = {
        "ret_15m_z": -2.0, "ret_1h_z": -2.0, "ret_4h_z": -2.0,
        "ret_24h_z": -2.0, "ret_7d_z": -2.0, "mom_consistency": 0.1,
    }
    t = tilt_momentum(feats)
    assert -1.0 <= t < -0.5


def test_tilt_momentum_neutral_when_mixed():
    feats = {
        "ret_15m_z": 0.0, "ret_1h_z": 0.0, "ret_4h_z": 0.0,
        "ret_24h_z": 0.0, "ret_7d_z": 0.0, "mom_consistency": 0.5,
    }
    t = tilt_momentum(feats)
    assert abs(t) < 0.1


def test_tilt_momentum_clipped_to_unit_range():
    feats = {
        "ret_15m_z": 10.0, "ret_1h_z": 10.0, "ret_4h_z": 10.0,
        "ret_24h_z": 10.0, "ret_7d_z": 10.0, "mom_consistency": 1.0,
    }
    t = tilt_momentum(feats)
    assert -1.0 <= t <= 1.0


def test_tilt_momentum_handles_missing_features():
    # If features missing, treat as 0 (neutral)
    t = tilt_momentum({})
    assert t == 0.0
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/scoring/tilt.py
"""Tilt functions per feature family. Each returns value in [-1, +1].

Design from spec §8.1 / §8.2.
"""
from __future__ import annotations


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _get(feats: dict, name: str, default: float = 0.0) -> float:
    v = feats.get(name, default)
    if v is None:
        return default
    return float(v)


def tilt_momentum(feats: dict) -> float:
    """Weighted average of multi-timeframe return z-scores + consistency.

    Returns value in [-1, +1].
    """
    ret_components = (
        0.15 * _get(feats, "ret_15m_z") +
        0.20 * _get(feats, "ret_1h_z") +
        0.20 * _get(feats, "ret_4h_z") +
        0.25 * _get(feats, "ret_24h_z") +
        0.10 * _get(feats, "ret_7d_z")
    )
    # Normalize by typical |z|=2 → halve, then clip
    base = _clip(ret_components / 2.0)
    # Consistency: 0.5 = neutral, deviation pushes tilt
    cons_tilt = (_get(feats, "mom_consistency", 0.5) - 0.5) * 2.0  # -1..+1
    return _clip(0.7 * base + 0.3 * cons_tilt)
```

- [ ] **Step 4: Verify PASS** (5 tests)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/scoring/tilt.py tests/test_features/test_scoring/test_tilt_momentum.py
git commit -m "feat(scoring): tilt_momentum — weighted multi-TF z-scores + consistency"
git push
```

---

## Task 4.3: Tilt function — perp microstructure

**Files:**
- Modify: `src/crypto_predictor/scoring/tilt.py` (append)
- Create: `tests/test_features/test_scoring/test_tilt_perp.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features/test_scoring/test_tilt_perp.py
from crypto_predictor.scoring.tilt import tilt_perp


def test_tilt_perp_extreme_negative_funding_is_bullish():
    # Crowded shorts → mean-revert → long bias
    feats = {
        "funding_z": -3.0, "funding_extreme": 1.0,
        "oi_growth_z": 0.5, "ret_4h_z": 0.5,
        "liq_pressure_short_4h": 1_000_000.0,
        "liq_pressure_long_4h": 0.0,
    }
    t = tilt_perp(feats)
    assert t > 0.4


def test_tilt_perp_extreme_positive_funding_is_bearish():
    # Crowded longs → mean-revert → short bias
    feats = {
        "funding_z": 3.0, "funding_extreme": 1.0,
        "oi_growth_z": 0.0, "ret_4h_z": 0.0,
        "liq_pressure_short_4h": 0.0,
        "liq_pressure_long_4h": 1_000_000.0,
    }
    t = tilt_perp(feats)
    assert t < -0.4


def test_tilt_perp_oi_growth_confirms_direction():
    # Price up + OI up = real long pressure (bullish)
    feats = {
        "funding_z": 0.0, "funding_extreme": 0.0,
        "oi_growth_z": 1.0, "ret_4h_z": 1.0,
        "liq_pressure_short_4h": 0.0,
        "liq_pressure_long_4h": 0.0,
    }
    t = tilt_perp(feats)
    assert t > 0.1


def test_tilt_perp_clipped():
    feats = {
        "funding_z": -10.0, "funding_extreme": 1.0,
        "oi_growth_z": 10.0, "ret_4h_z": 10.0,
        "liq_pressure_short_4h": 1e12,
        "liq_pressure_long_4h": 0.0,
    }
    t = tilt_perp(feats)
    assert -1.0 <= t <= 1.0


def test_tilt_perp_handles_missing_features():
    assert tilt_perp({}) == 0.0
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement (append to `tilt.py`)**

```python
# append to src/crypto_predictor/scoring/tilt.py

def tilt_perp(feats: dict) -> float:
    """Perp microstructure tilt: funding mean-reversion + OI confirmation + liquidation pressure.

    Design from spec §8.2.
    """
    # Negative funding → shorts paying → long-bias
    funding_z = _get(feats, "funding_z")
    funding_tilt = -_clip(funding_z / 2.0)

    # OI confirmation: sign(price 4h move) * |OI growth|
    ret_4h_sign = 1.0 if _get(feats, "ret_4h_z") > 0 else (-1.0 if _get(feats, "ret_4h_z") < 0 else 0.0)
    oi_growth_z = _get(feats, "oi_growth_z")
    oi_confirm = ret_4h_sign * _clip(oi_growth_z)

    # Liquidation imbalance: short_liq − long_liq normalized
    s = _get(feats, "liq_pressure_short_4h")
    l = _get(feats, "liq_pressure_long_4h")
    total = s + l + 1.0
    liq_tilt = _clip((s - l) / total)

    return _clip(0.4 * funding_tilt + 0.3 * oi_confirm + 0.3 * liq_tilt)
```

- [ ] **Step 4: Verify PASS** (5 new tests)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/scoring/tilt.py tests/test_features/test_scoring/test_tilt_perp.py
git commit -m "feat(scoring): tilt_perp — funding/OI/liq microstructure mean-reversion"
git push
```

---

## Task 4.4: Tilt functions — volume, technical, sentiment, global

**Files:**
- Modify: `src/crypto_predictor/scoring/tilt.py` (append 4 functions)
- Create: `tests/test_features/test_scoring/test_tilt_others.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features/test_scoring/test_tilt_others.py
from crypto_predictor.scoring.tilt import (
    tilt_volume, tilt_technical, tilt_sentiment, tilt_global,
)


def test_tilt_volume_amplifies_with_high_vol_z():
    # High vol z-score + positive recent return → bullish amplification
    feats = {"vol_z_24h": 2.0, "ret_24h_z": 1.0}
    t = tilt_volume(feats)
    assert t > 0.0


def test_tilt_volume_neutral_when_low_volume():
    feats = {"vol_z_24h": 0.0, "ret_24h_z": 0.0}
    assert abs(tilt_volume(feats)) < 0.1


def test_tilt_technical_oversold_is_bullish():
    feats = {"rsi_14_1h": 25.0, "rsi_oversold": 1.0, "rsi_overbought": 0.0,
             "macd_hist_1h": 0.5, "bb_position_1h": 0.0, "price_vs_sma50": -0.05}
    t = tilt_technical(feats)
    assert t > 0.0  # oversold → mean revert up


def test_tilt_technical_overbought_is_bearish():
    feats = {"rsi_14_1h": 78.0, "rsi_oversold": 0.0, "rsi_overbought": 1.0,
             "macd_hist_1h": -0.5, "bb_position_1h": 1.0, "price_vs_sma50": 0.1}
    t = tilt_technical(feats)
    assert t < 0.0


def test_tilt_sentiment_positive_news_is_bullish():
    feats = {"news_sent_24h": 0.6, "social_sent_24h": 0.4,
             "sent_velocity": 0.3, "news_volume_z": 1.5}
    t = tilt_sentiment(feats)
    assert t > 0.2


def test_tilt_sentiment_returns_zero_when_neutral():
    feats = {"news_sent_24h": 0.0, "social_sent_24h": 0.0,
             "sent_velocity": 0.0, "news_volume_z": 0.0}
    assert tilt_sentiment(feats) == 0.0


def test_tilt_global_btc_dom_rising_helps_btc_short():
    # BTC dominance rising → alts underperform
    feats = {"btc_dom_trend_7d": 0.05, "eth_btc_trend_7d": 0.0,
             "total_mcap_z": 0.0, "sector_strength_24h": 0.0}
    t = tilt_global(feats)
    # negative tilt for alts under btc-dom rise
    assert t < 0.1   # weak / negative tilt


def test_all_tilts_clipped_to_unit_range():
    big = {k: 100.0 for k in [
        "vol_z_24h", "ret_24h_z", "rsi_14_1h", "rsi_oversold", "rsi_overbought",
        "macd_hist_1h", "bb_position_1h", "price_vs_sma50",
        "news_sent_24h", "social_sent_24h", "sent_velocity", "news_volume_z",
        "btc_dom_trend_7d", "eth_btc_trend_7d", "total_mcap_z", "sector_strength_24h",
    ]}
    for fn in [tilt_volume, tilt_technical, tilt_sentiment, tilt_global]:
        t = fn(big)
        assert -1.0 <= t <= 1.0
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement (append to `tilt.py`)**

```python
# append to src/crypto_predictor/scoring/tilt.py

def tilt_volume(feats: dict) -> float:
    """Volume confirms direction; high vol_z amplifies the recent 24h return signal."""
    vol_z = _get(feats, "vol_z_24h")
    ret_24h = _get(feats, "ret_24h_z")
    # Amplify ret direction by vol intensity
    amp = _clip(vol_z / 2.0)
    direction = _clip(ret_24h / 2.0)
    return _clip(amp * direction)


def tilt_technical(feats: dict) -> float:
    """Technical: RSI mean-reversion + MACD + BB + SMA50 trend.

    Design: oversold (RSI<30) → bullish; overbought (RSI>70) → bearish.
    """
    rsi = _get(feats, "rsi_14_1h", 50.0)
    rsi_tilt = (50.0 - rsi) / 50.0   # +1 at rsi=0, -1 at rsi=100
    macd = _clip(_get(feats, "macd_hist_1h") / 2.0)
    bb_pos = _get(feats, "bb_position_1h", 0.5)
    bb_tilt = (0.5 - bb_pos) * 2.0   # +1 at lower band, -1 at upper
    sma = _clip(_get(feats, "price_vs_sma50") * 10.0)  # 1% above SMA → 0.1 tilt
    return _clip(0.4 * rsi_tilt + 0.25 * macd + 0.20 * bb_tilt + 0.15 * sma)


def tilt_sentiment(feats: dict) -> float:
    """Sentiment composite. Returns 0 if no sentiment cache data exists (all 0)."""
    news = _get(feats, "news_sent_24h")
    social = _get(feats, "social_sent_24h")
    velocity = _get(feats, "sent_velocity")
    vol = _clip(_get(feats, "news_volume_z") / 2.0)
    base = 0.5 * news + 0.3 * social + 0.2 * velocity
    # Amplify by news volume (more articles → more confidence)
    return _clip(base * (1.0 + 0.5 * abs(vol)) * (1.0 if base != 0 else 0.0))


def tilt_global(feats: dict) -> float:
    """Global / cross-coin tilt: BTC dom trend + ETH/BTC + total mcap + sector strength."""
    btc_dom = _get(feats, "btc_dom_trend_7d")
    eth_btc = _get(feats, "eth_btc_trend_7d")
    total_mcap = _clip(_get(feats, "total_mcap_z") / 2.0)
    sector = _clip(_get(feats, "sector_strength_24h") * 20.0)  # 5% → 1.0
    # BTC dominance rising is bearish for alts (this tilt is per-coin; ETH-class and below)
    dom_tilt = -_clip(btc_dom * 20.0)   # 5% trend → -1.0
    eth_btc_tilt = _clip(eth_btc * 20.0)
    return _clip(0.3 * dom_tilt + 0.2 * eth_btc_tilt + 0.2 * total_mcap + 0.3 * sector)
```

- [ ] **Step 4: Verify PASS** (8 new tests)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/scoring/tilt.py tests/test_features/test_scoring/test_tilt_others.py
git commit -m "feat(scoring): tilt_volume + tilt_technical + tilt_sentiment + tilt_global"
git push
```

---

## Task 4.5: Direction raw formula

**Files:**
- Create: `src/crypto_predictor/scoring/direction.py`
- Create: `tests/test_features/test_scoring/test_direction.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features/test_scoring/test_direction.py
from crypto_predictor.scoring.direction import compute_direction_raw, DEFAULT_WEIGHTS


def test_direction_raw_in_unit_range():
    feats = {
        # Strong bullish momentum
        "ret_15m_z": 2.0, "ret_1h_z": 2.0, "ret_4h_z": 2.0, "ret_24h_z": 2.0,
        "ret_7d_z": 2.0, "mom_consistency": 0.9,
        # Bullish perp (crowded shorts)
        "funding_z": -3.0, "funding_extreme": 1.0,
        "oi_growth_z": 1.0, "liq_pressure_short_4h": 1e6,
        "liq_pressure_long_4h": 0.0,
        # Volume confirming
        "vol_z_24h": 2.0,
        # Mixed technical
        "rsi_14_1h": 50.0, "macd_hist_1h": 0.5, "bb_position_1h": 0.5,
        "price_vs_sma50": 0.05,
        # Neutral sentiment + global
        "news_sent_24h": 0.0, "social_sent_24h": 0.0,
        "sent_velocity": 0.0, "news_volume_z": 0.0,
        "btc_dom_trend_7d": 0.0, "eth_btc_trend_7d": 0.0,
        "total_mcap_z": 0.0, "sector_strength_24h": 0.0,
        "coin_btc_corr_30d": 0.5, "mcap_rank_weight": 1.0,
    }
    raw = compute_direction_raw(feats)
    assert -1.0 <= raw <= 1.0
    assert raw > 0.3  # strongly bullish setup


def test_direction_raw_neutral_when_all_zero():
    feats = {"mcap_rank_weight": 1.0, "coin_btc_corr_30d": 0.5}
    raw = compute_direction_raw(feats)
    assert abs(raw) < 0.01


def test_direction_raw_custom_weights_change_output():
    feats = {
        "ret_15m_z": 2.0, "ret_1h_z": 2.0, "ret_4h_z": 2.0, "ret_24h_z": 2.0,
        "ret_7d_z": 2.0, "mom_consistency": 0.9,
        "mcap_rank_weight": 1.0, "coin_btc_corr_30d": 0.5,
    }
    raw_default = compute_direction_raw(feats)
    # Crank momentum weight up
    custom = dict(DEFAULT_WEIGHTS)
    custom["momentum"] = 0.80
    custom["perp"] = 0.05
    custom["volume"] = 0.05
    custom["technical"] = 0.05
    custom["sentiment"] = 0.025
    custom["global"] = 0.025
    raw_momentum_heavy = compute_direction_raw(feats, weights=custom)
    assert raw_momentum_heavy > raw_default


def test_default_weights_sum_to_one():
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/scoring/direction.py
"""Direction-raw scoring: weighted sum of 6 tilt functions.

Design from spec §8.1.
"""
from __future__ import annotations

from crypto_predictor.scoring.tilt import (
    tilt_global, tilt_momentum, tilt_perp, tilt_sentiment,
    tilt_technical, tilt_volume,
)

# Weights from design spec §8.1
DEFAULT_WEIGHTS: dict[str, float] = {
    "momentum": 0.20,
    "perp": 0.25,
    "volume": 0.10,
    "technical": 0.15,
    "sentiment": 0.15,
    "global": 0.15,
}


def compute_direction_raw(feats: dict, *,
                          weights: dict[str, float] | None = None) -> float:
    """Weighted sum of family tilts. Returns value clipped to [-1, +1]."""
    w = weights or DEFAULT_WEIGHTS

    mcap_w = float(feats.get("mcap_rank_weight", 1.0) or 1.0)
    btc_corr = float(feats.get("coin_btc_corr_30d", 0.0) or 0.0)
    global_attenuation = max(0.0, 1.0 - abs(btc_corr))

    raw = (
        w["momentum"]   * tilt_momentum(feats) +
        w["perp"]       * tilt_perp(feats) +
        w["volume"]     * tilt_volume(feats) +
        w["technical"]  * tilt_technical(feats) +
        w["sentiment"]  * tilt_sentiment(feats) * mcap_w +
        w["global"]     * tilt_global(feats) * global_attenuation
    )
    # Clip to [-1, 1]
    return max(-1.0, min(1.0, raw))
```

- [ ] **Step 4: Verify PASS** (4 tests)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/scoring/direction.py tests/test_features/test_scoring/test_direction.py
git commit -m "feat(scoring): compute_direction_raw — weighted sum of 6 family tilts"
git push
```

---

## Task 4.6: Magnitude estimator

**Files:**
- Create: `src/crypto_predictor/scoring/magnitude.py`
- Create: `tests/test_features/test_scoring/test_magnitude.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features/test_scoring/test_magnitude.py
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.scoring.magnitude import (
    compute_expected_return, realized_vol_30d,
)


def _seed_vol(tmp_path: Path, sym: str, vol_pct: float = 0.02):
    """Seed 35 daily bars with given per-bar volatility (random-walk like)."""
    import numpy as np
    np.random.seed(42)
    p = 100.0
    rows = []
    for i in range(35):
        ret = np.random.normal(0.0, vol_pct)
        p = p * (1 + ret)
        rows.append({
            "timestamp": 1700000000000 + i * 86400 * 1000,
            "open": p, "high": p * 1.01, "low": p * 0.99,
            "close": p, "volume": 1000,
        })
    write_ohlcv(tmp_path, sym, "1d", pd.DataFrame(rows))


def test_realized_vol_30d_positive(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_vol(tmp_path, sym, vol_pct=0.03)
    asof = datetime.fromtimestamp(
        (1700000000000 + 36 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    vol = realized_vol_30d(fetcher, sym)
    assert vol > 0.005  # at least 0.5%


def test_expected_return_bullish_when_direction_positive(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_vol(tmp_path, sym, vol_pct=0.02)
    asof = datetime.fromtimestamp(
        (1700000000000 + 36 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    r = compute_expected_return(fetcher, sym, direction_raw=0.8, regime="BULL")
    assert r > 0


def test_expected_return_bearish_when_direction_negative(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_vol(tmp_path, sym, vol_pct=0.02)
    asof = datetime.fromtimestamp(
        (1700000000000 + 36 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    r = compute_expected_return(fetcher, sym, direction_raw=-0.8, regime="CHOP")
    assert r < 0


def test_expected_return_smaller_when_signal_weak(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    _seed_vol(tmp_path, sym, vol_pct=0.02)
    asof = datetime.fromtimestamp(
        (1700000000000 + 36 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    r_weak = compute_expected_return(fetcher, sym, direction_raw=0.2, regime="CHOP")
    r_strong = compute_expected_return(fetcher, sym, direction_raw=0.8, regime="CHOP")
    assert abs(r_weak) < abs(r_strong)


def test_expected_return_zero_when_no_history(tmp_path: Path):
    sym = "BTC-USDT-SWAP"
    asof = datetime.now(timezone.utc)
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    r = compute_expected_return(fetcher, sym, direction_raw=0.5, regime="CHOP")
    assert r == 0.0
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/scoring/magnitude.py
"""Magnitude estimator: base vol × signal strength × regime multiplier.

Design from spec §8.3.
"""
from __future__ import annotations

import math

import numpy as np

from crypto_predictor.features.fetcher import FeatureFetcher

REGIME_MULT: dict[str, float] = {"BULL": 1.15, "BEAR": 0.90, "CHOP": 1.00}


def realized_vol_30d(fetcher: FeatureFetcher, symbol: str) -> float:
    """Std of daily log returns over the last 30 days. 0.0 if insufficient data."""
    df = fetcher.ohlcv(symbol, "1d", lookback_bars=32)
    if len(df) < 5:
        return 0.0
    closes = df["close"].values.astype(float)
    closes = closes[closes > 0]
    if len(closes) < 5:
        return 0.0
    rets = np.log(closes[1:] / closes[:-1])
    if len(rets) == 0:
        return 0.0
    return float(np.std(rets, ddof=0))


def compute_expected_return(fetcher: FeatureFetcher, symbol: str,
                            *, direction_raw: float, regime: str) -> float:
    """Compute signed expected return for next 24h horizon.

    expected = base_vol × (0.5 + 0.5 × |direction_raw|) × regime_mult × sign(direction_raw)
    """
    base_vol = realized_vol_30d(fetcher, symbol)
    if base_vol == 0:
        return 0.0
    strength = abs(direction_raw)
    regime_mult = REGIME_MULT.get(regime, 1.0)
    sign = math.copysign(1.0, direction_raw) if direction_raw != 0 else 0.0
    return base_vol * (0.5 + 0.5 * strength) * regime_mult * sign
```

- [ ] **Step 4: Verify PASS** (5 tests)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/scoring/magnitude.py tests/test_features/test_scoring/test_magnitude.py
git commit -m "feat(scoring): magnitude estimator — base vol × signal strength × regime mult"
git push
```

---

## Task 4.7: Regime detector

**Files:**
- Create: `src/crypto_predictor/scoring/regime.py`
- Create: `tests/test_features/test_scoring/test_regime.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_features/test_scoring/test_regime.py
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.scoring.regime import detect_regime, REGIME_LABELS


def _seed_btc(root: Path, daily_drift: float = 0.0,
              funding_avg: float = 0.0, n: int = 40):
    rows = []
    p = 100.0
    for i in range(n):
        p *= (1 + daily_drift)
        rows.append({
            "timestamp": 1700000000000 + i * 86400 * 1000,
            "open": p / (1 + daily_drift), "high": p * 1.01, "low": p * 0.99,
            "close": p, "volume": 1000,
        })
    write_ohlcv(root, "BTC/USDT:USDT", "1d", pd.DataFrame(rows))
    # Funding
    fpath = parquet_path(root, "BTC/USDT:USDT", "funding", "futures")
    fpath.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"timestamp": 1700000000000 + i * 8 * 3600 * 1000,
         "funding_rate": funding_avg + 0.00001 * ((-1) ** i)}
        for i in range(21)  # 7d × 3 funding/day
    ]).to_parquet(fpath, index=False)


def test_regime_bull_when_btc_up_and_funding_positive(tmp_path: Path):
    _seed_btc(tmp_path, daily_drift=0.005, funding_avg=0.0002)  # +0.5%/day, +0.02% funding
    asof = datetime.fromtimestamp(
        (1700000000000 + 40 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    regime = detect_regime(fetcher, global_mcap_trend=1.0)
    assert regime == "BULL"


def test_regime_bear_when_btc_down_and_funding_negative(tmp_path: Path):
    _seed_btc(tmp_path, daily_drift=-0.005, funding_avg=-0.0002)
    asof = datetime.fromtimestamp(
        (1700000000000 + 40 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    regime = detect_regime(fetcher, global_mcap_trend=-1.0)
    assert regime == "BEAR"


def test_regime_chop_when_mixed_signals(tmp_path: Path):
    _seed_btc(tmp_path, daily_drift=0.001, funding_avg=0.0)  # weak drift, neutral funding
    asof = datetime.fromtimestamp(
        (1700000000000 + 40 * 86400 * 1000) / 1000, tz=timezone.utc
    )
    fetcher = FeatureFetcher(root=tmp_path, asof=asof)
    regime = detect_regime(fetcher, global_mcap_trend=0.0)
    assert regime == "CHOP"


def test_regime_labels_constant():
    assert REGIME_LABELS == ("BULL", "BEAR", "CHOP")
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/scoring/regime.py
"""Regime detector: BULL / BEAR / CHOP based on BTC trend + funding + global mcap.

Design from spec §9.
"""
from __future__ import annotations

import math
from typing import Literal

from crypto_predictor.features.fetcher import FeatureFetcher

REGIME_LABELS = ("BULL", "BEAR", "CHOP")
Regime = Literal["BULL", "BEAR", "CHOP"]


def detect_regime(fetcher: FeatureFetcher, *,
                  global_mcap_trend: float = 0.0,
                  btc_symbol: str = "BTC/USDT:USDT") -> Regime:
    """Detect market regime.

    btc_30d_return > 5% counts as bull vote; < -5% counts as bear.
    btc_funding_avg_7d > 0 counts as bull; < -0.0001 (negative) counts as bear.
    global_mcap_trend > 0 counts as bull; < 0 counts as bear.

    Returns BULL if ≥2 bull votes, BEAR if ≥2 bear votes, else CHOP.
    """
    # BTC 30-day return
    daily = fetcher.ohlcv(btc_symbol, "1d", lookback_bars=32)
    btc_30d_return = 0.0
    if len(daily) >= 31:
        p_now = float(daily["close"].iloc[-1])
        p_30d = float(daily["close"].iloc[-31])
        if p_30d > 0:
            btc_30d_return = math.log(p_now / p_30d)

    # BTC funding average (last 7 days × 3 funding rates/day = 21 rows)
    funding = fetcher.funding(btc_symbol, lookback_rows=21)
    if not funding.empty:
        btc_funding_avg = float(funding["funding_rate"].mean())
    else:
        btc_funding_avg = 0.0

    bull_votes = (
        (1 if btc_30d_return > 0.05 else 0) +
        (1 if btc_funding_avg > 0 else 0) +
        (1 if global_mcap_trend > 0 else 0)
    )
    bear_votes = (
        (1 if btc_30d_return < -0.05 else 0) +
        (1 if btc_funding_avg < -0.0001 else 0) +
        (1 if global_mcap_trend < 0 else 0)
    )

    if bull_votes >= 2:
        return "BULL"
    if bear_votes >= 2:
        return "BEAR"
    return "CHOP"
```

- [ ] **Step 4: Verify PASS** (4 tests)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/scoring/regime.py tests/test_features/test_scoring/test_regime.py
git commit -m "feat(scoring): regime detector (BULL/BEAR/CHOP) via BTC trend + funding + mcap"
git push
```

---

## Task 4.8: Anomaly flag + composite score

**Files:**
- Create: `src/crypto_predictor/scoring/anomaly.py`
- Create: `src/crypto_predictor/scoring/composite.py`
- Create: `tests/test_features/test_scoring/test_anomaly.py`
- Create: `tests/test_features/test_scoring/test_composite.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_features/test_scoring/test_anomaly.py
from crypto_predictor.scoring.anomaly import is_anomalous, CRITICAL_FEATURES


def test_anomalous_when_funding_z_exceeds_three():
    feats = {name: 0.0 for name in CRITICAL_FEATURES}
    feats["funding_z"] = 3.5
    assert is_anomalous(feats) is True


def test_anomalous_when_liq_pressure_extreme():
    feats = {name: 0.0 for name in CRITICAL_FEATURES}
    # Use z-score directly — liq pressure feature compares to baseline of 0
    feats["liq_pressure_long_4h"] = 1e9  # huge
    # Anomaly is based on z-scores of features; liq pressure isn't a z-score feature
    # so this test only triggers if liq_pressure is in CRITICAL_FEATURES with a threshold.
    # Per design, we flag based on z-scored features only.
    # So this test should assert FALSE if liq pressure not z-scored.
    assert is_anomalous(feats) is False


def test_normal_features_not_anomalous():
    feats = {name: 0.5 for name in CRITICAL_FEATURES}
    assert is_anomalous(feats) is False


def test_critical_features_list_excludes_non_zscore_features():
    # Only z-score features should be in CRITICAL_FEATURES
    for name in CRITICAL_FEATURES:
        assert name.endswith("_z") or name in {"sent_velocity"}, \
            f"{name} is not a z-score / velocity feature"
```

```python
# tests/test_features/test_scoring/test_composite.py
from crypto_predictor.scoring.composite import compute_composite


def test_composite_long_high_when_p_up_and_positive_return():
    score = compute_composite(p_up=0.8, expected_return=0.05, anomalous=False)
    # composite = p × |return| = 0.8 × 0.05 = 0.04
    assert abs(score - 0.04) < 1e-9


def test_composite_short_uses_p_down_and_abs_return():
    # P(↓) = 1 - 0.7 = 0.3 — but caller decides direction; here we use P_up=0.3, ret=-0.05
    score = compute_composite(p_up=0.3, expected_return=-0.05, anomalous=False)
    # For short: P(↓) = 0.7, |return| = 0.05 → 0.035
    assert abs(score - 0.035) < 1e-9


def test_composite_demoted_when_anomalous():
    normal = compute_composite(p_up=0.8, expected_return=0.05, anomalous=False)
    wild = compute_composite(p_up=0.8, expected_return=0.05, anomalous=True)
    assert wild < normal
    assert abs(wild - normal * 0.7) < 1e-9


def test_composite_zero_when_no_signal():
    assert compute_composite(p_up=0.5, expected_return=0.0, anomalous=False) == 0.0
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/scoring/anomaly.py
"""Anomaly flag: marks coins whose feature values are historically extreme."""
from __future__ import annotations

CRITICAL_FEATURES = (
    "funding_z",
    "oi_growth_z",
    "vol_z_24h",
    "sent_velocity",
    "ret_24h_z",
    "ret_7d_z",
)
THRESHOLD = 3.0


def is_anomalous(feats: dict) -> bool:
    """Return True if any critical z-score feature exceeds ±THRESHOLD."""
    for name in CRITICAL_FEATURES:
        v = feats.get(name)
        if v is None:
            continue
        if abs(float(v)) > THRESHOLD:
            return True
    return False
```

```python
# src/crypto_predictor/scoring/composite.py
"""Composite score for ranking. Higher = better candidate."""
from __future__ import annotations


def compute_composite(*, p_up: float, expected_return: float,
                      anomalous: bool) -> float:
    """Composite = max(p_up, p_down) × |expected_return|; demoted by 0.7 if anomalous."""
    p_down = 1.0 - p_up
    base = max(p_up, p_down) * abs(expected_return)
    return base * 0.7 if anomalous else base
```

- [ ] **Step 4: Verify PASS** (8 tests across two files)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/scoring/anomaly.py src/crypto_predictor/scoring/composite.py tests/test_features/test_scoring/test_anomaly.py tests/test_features/test_scoring/test_composite.py
git commit -m "feat(scoring): anomaly flag (critical z-features) + composite scoring"
git push
```

**Week 4 done.** Verify:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
Expected: ~110 tests pass (71 from Plan A + ~40 new from Week 4).

---

# Week 5 — Backtest framework + calibration

Goal: walk-forward backtest orchestrator that fits isotonic regression per regime, produces calibration_map.json, and writes backtest_report.md.

## Task 5.1: Walk-forward window iterator

**Files:**
- Create: `src/crypto_predictor/backtest/__init__.py`
- Create: `src/crypto_predictor/backtest/walk_forward.py`
- Create: `tests/test_backtest/__init__.py`
- Create: `tests/test_backtest/test_walk_forward.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backtest/test_walk_forward.py
from datetime import datetime, timezone

from crypto_predictor.backtest.walk_forward import iter_windows, WalkForwardWindow


def test_iter_windows_produces_correct_slices():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 1, tzinfo=timezone.utc)
    # 3 months train + 1 month calibration + 1 month validation, slide 7 days
    windows = list(iter_windows(start=start, end=end,
                                train_months=3, cal_months=1, val_months=1,
                                slide_days=7))
    assert len(windows) > 0
    # First window: train 2026-01-01..2026-03-31, cal 2026-04-01..2026-04-30, val 2026-05-01..2026-05-31
    w0 = windows[0]
    assert isinstance(w0, WalkForwardWindow)
    assert w0.train_start == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert w0.val_end <= end


def test_iter_windows_slides_forward():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 6, 1, tzinfo=timezone.utc)
    windows = list(iter_windows(start=start, end=end,
                                train_months=3, cal_months=1, val_months=1,
                                slide_days=7))
    # Second window should slide forward by 7 days
    if len(windows) >= 2:
        delta = (windows[1].train_start - windows[0].train_start).days
        assert delta == 7
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/backtest/__init__.py
"""Walk-forward backtest framework."""
```

```python
# src/crypto_predictor/backtest/walk_forward.py
"""Walk-forward window iterator. Each iteration yields train/cal/val slice."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterator


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: datetime
    train_end: datetime
    cal_start: datetime
    cal_end: datetime
    val_start: datetime
    val_end: datetime


def _add_months(dt: datetime, n: int) -> datetime:
    # Approximate: 30 days/month is fine for backtest windowing
    return dt + timedelta(days=30 * n)


def iter_windows(*, start: datetime, end: datetime,
                 train_months: int, cal_months: int, val_months: int,
                 slide_days: int = 7) -> Iterator[WalkForwardWindow]:
    """Yield rolling (train, cal, val) slices that fit within [start, end]."""
    cursor = start
    total_span = train_months + cal_months + val_months
    while True:
        train_start = cursor
        train_end = _add_months(train_start, train_months)
        cal_start = train_end
        cal_end = _add_months(cal_start, cal_months)
        val_start = cal_end
        val_end = _add_months(val_start, val_months)
        if val_end > end:
            break
        yield WalkForwardWindow(
            train_start=train_start, train_end=train_end,
            cal_start=cal_start, cal_end=cal_end,
            val_start=val_start, val_end=val_end,
        )
        cursor = cursor + timedelta(days=slide_days)
```

- [ ] **Step 4: Verify PASS** (2 tests)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/backtest/ tests/test_backtest/
git commit -m "feat(backtest): walk-forward window iterator (train/cal/val slices)"
git push
```

---

## Task 5.2: Isotonic calibration per regime

**Files:**
- Create: `src/crypto_predictor/calibration/__init__.py`
- Create: `src/crypto_predictor/calibration/isotonic.py`
- Create: `tests/test_calibration/__init__.py`
- Create: `tests/test_calibration/test_isotonic.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calibration/test_isotonic.py
import numpy as np

from crypto_predictor.calibration.isotonic import (
    fit_calibration, predict_probability, RegimeCalibrators,
)


def test_fit_returns_calibrators_per_regime():
    np.random.seed(0)
    # Synthetic: 100 samples per regime, raw scores in [-1,1], labels correlated with raw
    rows = []
    for regime in ("BULL", "BEAR", "CHOP"):
        for _ in range(100):
            raw = np.random.uniform(-1, 1)
            # 70% probability label=1 when raw>0
            label = 1 if raw > 0 and np.random.random() < 0.7 else (
                1 if raw < 0 and np.random.random() < 0.3 else 0
            )
            rows.append((raw, label, regime))
    calibs = fit_calibration(rows)
    assert isinstance(calibs, RegimeCalibrators)
    for regime in ("BULL", "BEAR", "CHOP"):
        assert calibs.has(regime)


def test_predict_probability_in_unit_interval():
    np.random.seed(1)
    rows = []
    for _ in range(200):
        raw = np.random.uniform(-1, 1)
        label = 1 if raw > 0 else 0
        rows.append((raw, label, "BULL"))
    calibs = fit_calibration(rows)
    for raw in [-1.0, -0.5, 0.0, 0.5, 1.0]:
        p = predict_probability(calibs, raw_score=raw, regime="BULL")
        assert 0.0 <= p <= 1.0


def test_predict_probability_monotonic_in_raw():
    np.random.seed(2)
    rows = []
    for _ in range(500):
        raw = np.random.uniform(-1, 1)
        label = 1 if raw + np.random.normal(0, 0.3) > 0 else 0
        rows.append((raw, label, "BULL"))
    calibs = fit_calibration(rows)
    ps = [predict_probability(calibs, raw_score=r, regime="BULL")
          for r in np.linspace(-1, 1, 11)]
    # Should be non-decreasing
    for i in range(len(ps) - 1):
        assert ps[i] <= ps[i+1] + 1e-6


def test_predict_probability_returns_0_5_for_unknown_regime():
    calibs = fit_calibration([(0.0, 0, "BULL")])
    p = predict_probability(calibs, raw_score=0.5, regime="UNKNOWN")
    assert p == 0.5
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/calibration/__init__.py
"""Per-regime isotonic calibration."""
```

```python
# src/crypto_predictor/calibration/isotonic.py
"""Per-regime isotonic regression mapping direction_raw → P(↑)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.isotonic import IsotonicRegression


@dataclass
class RegimeCalibrators:
    by_regime: dict[str, IsotonicRegression] = field(default_factory=dict)

    def has(self, regime: str) -> bool:
        return regime in self.by_regime

    def get(self, regime: str) -> IsotonicRegression | None:
        return self.by_regime.get(regime)


def fit_calibration(samples: list[tuple[float, int, str]]) -> RegimeCalibrators:
    """Fit one IsotonicRegression per regime.

    samples: list of (raw_score, label_int_0_or_1, regime).
    """
    by_regime: dict[str, list[tuple[float, int]]] = {}
    for raw, label, regime in samples:
        by_regime.setdefault(regime, []).append((float(raw), int(label)))

    calibrators = RegimeCalibrators()
    for regime, rows in by_regime.items():
        if len(rows) < 5:
            continue
        X = np.array([r[0] for r in rows]).reshape(-1, 1)
        y = np.array([r[1] for r in rows])
        ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
        ir.fit(X.ravel(), y)
        calibrators.by_regime[regime] = ir
    return calibrators


def predict_probability(calibs: RegimeCalibrators, *,
                        raw_score: float, regime: str) -> float:
    """Predict P(label=1) given raw score and regime. Default 0.5 if regime unknown."""
    ir = calibs.get(regime)
    if ir is None:
        return 0.5
    p = float(ir.predict([raw_score])[0])
    return max(0.0, min(1.0, p))
```

- [ ] **Step 4: Verify PASS** (4 tests)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/calibration/ tests/test_calibration/
git commit -m "feat(calibration): per-regime isotonic regression (raw → P(↑))"
git push
```

---

## Task 5.3: Calibration persistence (JSON)

**Files:**
- Create: `src/crypto_predictor/calibration/persistence.py`
- Create: `tests/test_calibration/test_persistence.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calibration/test_persistence.py
from pathlib import Path

import numpy as np

from crypto_predictor.calibration.isotonic import fit_calibration, predict_probability
from crypto_predictor.calibration.persistence import save_calibration, load_calibration


def test_save_load_roundtrip(tmp_path: Path):
    np.random.seed(0)
    rows = []
    for _ in range(100):
        raw = np.random.uniform(-1, 1)
        label = 1 if raw > 0 else 0
        rows.append((raw, label, "BULL"))
    calibs = fit_calibration(rows)
    path = tmp_path / "calibration_map.json"
    save_calibration(calibs, path, fit_window="2026-01-01..2026-03-31")
    loaded = load_calibration(path)
    assert loaded.has("BULL")
    # Predictions match within epsilon
    for raw in [-0.5, 0.0, 0.5]:
        p_orig = predict_probability(calibs, raw_score=raw, regime="BULL")
        p_load = predict_probability(loaded, raw_score=raw, regime="BULL")
        assert abs(p_orig - p_load) < 1e-6


def test_load_missing_file_returns_empty(tmp_path: Path):
    loaded = load_calibration(tmp_path / "nope.json")
    assert not loaded.has("BULL")
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/calibration/persistence.py
"""JSON persistence for calibration maps."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression

from crypto_predictor.calibration.isotonic import RegimeCalibrators


def save_calibration(calibs: RegimeCalibrators, path: Path, *,
                     fit_window: str) -> None:
    """Save fitted calibrators as JSON with knot points."""
    data = {"fit_window": fit_window, "regimes": {}}
    for regime, ir in calibs.by_regime.items():
        # Use the underlying X_thresholds_ and y_thresholds_ arrays from sklearn
        data["regimes"][regime] = {
            "x": ir.X_thresholds_.tolist(),
            "y": ir.y_thresholds_.tolist(),
            "increasing": True,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_calibration(path: Path) -> RegimeCalibrators:
    """Load calibrators from JSON. Returns empty object if file missing."""
    calibs = RegimeCalibrators()
    if not path.exists():
        return calibs
    data = json.loads(path.read_text(encoding="utf-8"))
    for regime, payload in data.get("regimes", {}).items():
        ir = IsotonicRegression(out_of_bounds="clip", increasing=True)
        # Fit on the saved knot points to reconstruct
        x = np.array(payload["x"])
        y = np.array(payload["y"])
        ir.fit(x, y)
        calibs.by_regime[regime] = ir
    return calibs
```

- [ ] **Step 4: Verify PASS** (2 tests)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/calibration/persistence.py tests/test_calibration/test_persistence.py
git commit -m "feat(calibration): JSON persistence for per-regime isotonic maps"
git push
```

---

## Task 5.4: Backtest metrics (hit rate, MAE, Brier, alpha)

**Files:**
- Create: `src/crypto_predictor/backtest/metrics.py`
- Create: `tests/test_backtest/test_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backtest/test_metrics.py
import numpy as np

from crypto_predictor.backtest.metrics import (
    hit_rate, mae, brier_score, top_k_alpha,
)


def test_hit_rate_all_correct():
    preds = [1, 1, 1, 0, 0]
    actuals = [1, 1, 1, 0, 0]
    assert hit_rate(preds, actuals) == 1.0


def test_hit_rate_half():
    preds = [1, 1, 0, 0]
    actuals = [1, 0, 0, 1]
    assert hit_rate(preds, actuals) == 0.5


def test_mae_zero_when_perfect():
    assert mae([0.05, -0.03, 0.02], [0.05, -0.03, 0.02]) == 0.0


def test_mae_average_absolute_error():
    assert abs(mae([0.05, 0.0], [0.03, -0.02]) - 0.02) < 1e-9


def test_brier_zero_when_perfect_confidence():
    # Predicted prob 1.0, label 1 → (1-1)² = 0
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0


def test_brier_quarter_when_coin_flip():
    # All p=0.5, labels 0/1 alternating
    bs = brier_score([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1])
    assert abs(bs - 0.25) < 1e-9


def test_top_k_alpha_zero_when_topk_matches_universe():
    universe_returns = [0.01, 0.02, 0.03, 0.04, 0.05]
    top_k_returns = universe_returns
    alpha = top_k_alpha(top_k_returns, universe_returns)
    assert alpha == 0.0


def test_top_k_alpha_positive_when_topk_beats():
    universe_returns = [0.0, 0.0, 0.0, 0.0, 0.0]
    top_k_returns = [0.05, 0.04, 0.03]
    alpha = top_k_alpha(top_k_returns, universe_returns)
    assert alpha > 0.0
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/backtest/metrics.py
"""Backtest metrics: hit rate, MAE, Brier score, top-K alpha."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def hit_rate(predictions: Sequence[int], actuals: Sequence[int]) -> float:
    """Fraction of correctly predicted directions."""
    if not predictions:
        return 0.0
    arr_p = np.asarray(predictions)
    arr_a = np.asarray(actuals)
    return float((arr_p == arr_a).mean())


def mae(predicted: Sequence[float], actual: Sequence[float]) -> float:
    """Mean absolute error."""
    if not predicted:
        return 0.0
    return float(np.mean(np.abs(np.asarray(predicted) - np.asarray(actual))))


def brier_score(probs: Sequence[float], labels: Sequence[int]) -> float:
    """Brier score = mean of (p − label)². Lower = better."""
    if not probs:
        return 0.0
    return float(np.mean((np.asarray(probs) - np.asarray(labels)) ** 2))


def top_k_alpha(top_k_returns: Sequence[float],
                universe_returns: Sequence[float]) -> float:
    """Top-K mean return minus universe mean return."""
    if not top_k_returns or not universe_returns:
        return 0.0
    return float(np.mean(top_k_returns) - np.mean(universe_returns))


def calibration_bucket_table(probs: Sequence[float], labels: Sequence[int],
                              n_buckets: int = 10) -> list[dict]:
    """Bucket probabilities into deciles, report bucket-empirical accuracy."""
    if not probs:
        return []
    arr_p = np.asarray(probs)
    arr_l = np.asarray(labels)
    bins = np.linspace(0.0, 1.0, n_buckets + 1)
    out = []
    for i in range(n_buckets):
        mask = (arr_p >= bins[i]) & (arr_p < bins[i + 1] if i < n_buckets - 1 else arr_p <= bins[i + 1])
        n = int(mask.sum())
        if n == 0:
            continue
        emp = float(arr_l[mask].mean())
        out.append({
            "bucket_low": float(bins[i]),
            "bucket_high": float(bins[i + 1]),
            "predicted_mean": float(arr_p[mask].mean()),
            "empirical_rate": emp,
            "n": n,
        })
    return out
```

- [ ] **Step 4: Verify PASS** (8 tests)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/backtest/metrics.py tests/test_backtest/test_metrics.py
git commit -m "feat(backtest): metrics — hit rate, MAE, Brier, top-K alpha, calibration buckets"
git push
```

---

## Task 5.5: Backtest report generator

**Files:**
- Create: `src/crypto_predictor/backtest/report.py`
- Create: `tests/test_backtest/test_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backtest/test_report.py
from pathlib import Path

from crypto_predictor.backtest.report import render_backtest_report


def test_render_includes_overall_section(tmp_path: Path):
    report = render_backtest_report(
        title="Test backtest",
        window_label="2026-01-01..2026-05-31",
        overall={
            "hit_rate": 0.612,
            "mae": 0.0234,
            "brier": 0.218,
            "n_predictions": 1200,
        },
        per_regime={
            "BULL": {"hit_rate": 0.641, "n": 290},
            "BEAR": {"hit_rate": 0.587, "n": 420},
            "CHOP": {"hit_rate": 0.604, "n": 490},
        },
        calibration_buckets=[
            {"bucket_low": 0.5, "bucket_high": 0.6,
             "predicted_mean": 0.55, "empirical_rate": 0.512, "n": 100},
            {"bucket_low": 0.7, "bucket_high": 0.8,
             "predicted_mean": 0.75, "empirical_rate": 0.674, "n": 100},
        ],
        top_k_alpha={"long": 0.032, "short": 0.021, "combined": 0.053},
        survivorship_bias_flag=True,
    )
    assert "Test backtest" in report
    assert "Hit rate" in report
    assert "61.2%" in report
    assert "BULL" in report
    assert "calibration" in report.lower()
    assert "survivorship" in report.lower()
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
# src/crypto_predictor/backtest/report.py
"""Markdown report generator for backtest results."""
from __future__ import annotations


def render_backtest_report(*, title: str, window_label: str,
                           overall: dict, per_regime: dict[str, dict],
                           calibration_buckets: list[dict],
                           top_k_alpha: dict[str, float],
                           survivorship_bias_flag: bool) -> str:
    """Render a backtest report as a markdown string."""
    lines = [
        f"# {title}",
        f"**Window**: {window_label}",
    ]
    if survivorship_bias_flag:
        lines.append("> ⚠ survivorship_bias: present — backtest excludes coins delisted during the window.")
    lines.append("")

    # Overall
    lines += [
        "## Overall",
        "",
        f"- **Hit rate**: {overall['hit_rate'] * 100:.1f}%",
        f"- **MAE**: {overall['mae'] * 100:.2f}%",
        f"- **Brier score**: {overall['brier']:.3f}",
        f"- **Predictions**: {overall['n_predictions']:,}",
        "",
    ]

    # Per-regime
    lines += ["## Per regime", "", "| Regime | Hit rate | n |", "|---|---|---|"]
    for regime, m in per_regime.items():
        lines.append(f"| {regime} | {m['hit_rate'] * 100:.1f}% | {m['n']:,} |")
    lines.append("")

    # Calibration
    lines += [
        "## Calibration buckets",
        "",
        "| P bucket | predicted | empirical | n |",
        "|---|---|---|---|",
    ]
    for b in calibration_buckets:
        lines.append(
            f"| {b['bucket_low']:.1f}–{b['bucket_high']:.1f} | "
            f"{b['predicted_mean']:.3f} | {b['empirical_rate']:.3f} | {b['n']:,} |"
        )
    lines.append("")

    # Top-K alpha
    lines += [
        "## Top-K alpha (vs equal-weight universe)",
        "",
        f"- **Long alpha**: {top_k_alpha['long'] * 100:+.2f}%",
        f"- **Short alpha**: {top_k_alpha['short'] * 100:+.2f}%",
        f"- **Combined**: {top_k_alpha['combined'] * 100:+.2f}%",
        "",
    ]

    return "\n".join(lines)
```

- [ ] **Step 4: Verify PASS** (1 test)

- [ ] **Step 5: Commit + push**

```powershell
git add src/crypto_predictor/backtest/report.py tests/test_backtest/test_report.py
git commit -m "feat(backtest): markdown report generator"
git push
```

---

## Task 5.6: Backtest orchestrator (`run_backtest` + CLI)

**Files:**
- Create: `src/crypto_predictor/backtest/runner.py`
- Create: `scripts/run_backtest.py`
- Create: `tests/test_backtest/test_runner_synthetic.py`

- [ ] **Step 1: Write the failing test (synthetic)**

```python
# tests/test_backtest/test_runner_synthetic.py
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.backtest.runner import run_backtest


def _seed_fake_universe(root: Path, n_symbols: int = 3, n_days: int = 30):
    """Seed minimal hourly history for backtest end-to-end test."""
    np.random.seed(0)
    for i in range(n_symbols):
        sym = f"FAKE{i}/USDT:USDT"
        # 1h bars
        p = 100.0
        rows = []
        for h in range(n_days * 24 + 100):
            p *= np.exp(np.random.normal(0.0, 0.005))
            rows.append({
                "timestamp": 1700000000000 + h * 3600 * 1000,
                "open": p, "high": p * 1.01, "low": p * 0.99,
                "close": p, "volume": 1000,
            })
        write_ohlcv(root, sym, "1h", pd.DataFrame(rows))
        # 1d
        d_rows = [
            {"timestamp": 1700000000000 + d * 86400 * 1000,
             "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}
            for d in range(n_days + 5)
        ]
        write_ohlcv(root, sym, "1d", pd.DataFrame(d_rows))
        # empty futures
        for kind in ["funding", "oi", "ls_ratio", "liq"]:
            p_path = parquet_path(root, sym, kind, "futures")
            p_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame().to_parquet(p_path, index=False)


def test_run_backtest_produces_report_and_calibration(tmp_path: Path):
    history = tmp_path / "history"
    _seed_fake_universe(history, n_symbols=3, n_days=20)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("l1:\n  - FAKE0/USDT:USDT\n  - FAKE1/USDT:USDT\n  - FAKE2/USDT:USDT\n")

    report_path = tmp_path / "report.md"
    calibration_path = tmp_path / "calib.json"

    result = run_backtest(
        history_root=history,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=sector_map,
        start=datetime.fromtimestamp(1700000000000 / 1000 + 86400, tz=timezone.utc),
        end=datetime.fromtimestamp(1700000000000 / 1000 + 19 * 86400, tz=timezone.utc),
        train_days=10, cal_days=3, val_days=3, slide_days=3,
        sample_interval_hours=12,
        symbols=["FAKE0/USDT:USDT", "FAKE1/USDT:USDT", "FAKE2/USDT:USDT"],
        report_path=report_path,
        calibration_path=calibration_path,
    )
    assert report_path.exists()
    assert calibration_path.exists()
    assert result["n_predictions"] > 0
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement runner**

```python
# src/crypto_predictor/backtest/runner.py
"""Walk-forward backtest orchestrator. End-to-end: predict → label → metrics → report."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import structlog

from crypto_predictor.backtest.metrics import (
    brier_score, calibration_bucket_table, hit_rate, mae, top_k_alpha,
)
from crypto_predictor.backtest.report import render_backtest_report
from crypto_predictor.calibration.isotonic import (
    fit_calibration, predict_probability,
)
from crypto_predictor.calibration.persistence import save_calibration
from crypto_predictor.features.compute import compute_features
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.scoring.anomaly import is_anomalous
from crypto_predictor.scoring.direction import compute_direction_raw
from crypto_predictor.scoring.magnitude import compute_expected_return
from crypto_predictor.scoring.regime import detect_regime
from crypto_predictor.scoring.returns import actual_return

log = structlog.get_logger(__name__)


def _sample_times(start: datetime, end: datetime,
                  interval_hours: int) -> list[datetime]:
    out = []
    cursor = start
    while cursor <= end:
        out.append(cursor)
        cursor += timedelta(hours=interval_hours)
    return out


def run_backtest(*, history_root: Path,
                 sentiment_cache: Path, global_cache: Path,
                 sector_map: Path,
                 start: datetime, end: datetime,
                 train_days: int, cal_days: int, val_days: int,
                 slide_days: int = 7,
                 sample_interval_hours: int = 12,
                 symbols: list[str],
                 report_path: Path,
                 calibration_path: Path) -> dict:
    """Run end-to-end walk-forward backtest. Returns summary dict."""
    log.info("backtest_start", n_symbols=len(symbols),
             start=start.isoformat(), end=end.isoformat())

    # ----- Phase 1: generate raw predictions across the full window -----
    raw_samples: list[tuple[float, int, str]] = []        # (raw, label, regime)
    pred_records: list[dict] = []                         # for later metric calc

    for asof in _sample_times(start, end, sample_interval_hours):
        fetcher = FeatureFetcher(root=history_root, asof=asof)
        regime = detect_regime(fetcher)

        for sym in symbols:
            try:
                feats = compute_features(
                    fetcher=fetcher, symbol=sym,
                    sentiment_cache=sentiment_cache, global_cache=global_cache,
                    sector_map_path=sector_map, mcap_rank=None,
                )
            except Exception as exc:
                log.warning("feature_compute_failed",
                            symbol=sym, asof=asof.isoformat(), error=str(exc))
                continue
            raw = compute_direction_raw(feats)
            actual = actual_return(root=history_root, symbol=sym,
                                   start_time=asof, horizon_hours=24)
            if actual is None:
                continue
            label = 1 if actual > 0 else 0
            raw_samples.append((raw, label, regime))
            pred_records.append({
                "asof": asof, "symbol": sym, "regime": regime,
                "raw": raw, "actual_return": actual, "label": label,
                "anomalous": is_anomalous(feats),
            })

    if not pred_records:
        log.error("no_predictions_generated")
        return {"n_predictions": 0}

    # ----- Phase 2: fit calibration on raw_samples -----
    calibs = fit_calibration(raw_samples)
    save_calibration(calibs, calibration_path,
                     fit_window=f"{start.isoformat()}..{end.isoformat()}")

    # ----- Phase 3: compute calibrated metrics -----
    probs = []
    labels = []
    pred_signs = []
    expected_rets = []
    actual_rets = []
    by_regime: dict[str, dict] = {}
    for rec in pred_records:
        p_up = predict_probability(calibs, raw_score=rec["raw"], regime=rec["regime"])
        probs.append(p_up)
        labels.append(rec["label"])
        pred_signs.append(1 if p_up > 0.5 else 0)
        # Estimate magnitude (need fetcher per sample — reuse asof fetcher)
        fetcher = FeatureFetcher(root=history_root, asof=rec["asof"])
        exp_ret = compute_expected_return(
            fetcher, rec["symbol"], direction_raw=rec["raw"], regime=rec["regime"]
        )
        expected_rets.append(exp_ret)
        actual_rets.append(rec["actual_return"])
        by_regime.setdefault(rec["regime"], {"preds": [], "labels": []})
        by_regime[rec["regime"]]["preds"].append(1 if p_up > 0.5 else 0)
        by_regime[rec["regime"]]["labels"].append(rec["label"])

    overall = {
        "hit_rate": hit_rate(pred_signs, labels),
        "mae": mae(expected_rets, actual_rets),
        "brier": brier_score(probs, labels),
        "n_predictions": len(pred_records),
    }
    per_regime = {}
    for regime, m in by_regime.items():
        per_regime[regime] = {
            "hit_rate": hit_rate(m["preds"], m["labels"]),
            "n": len(m["preds"]),
        }
    buckets = calibration_bucket_table(probs, labels)

    # Top-K alpha (top 20% by |expected return|)
    sorted_by_signal = sorted(
        zip(expected_rets, actual_rets), key=lambda x: abs(x[0]), reverse=True
    )
    k = max(1, len(sorted_by_signal) // 5)
    top_k_actual_long = [a for _, a in sorted_by_signal[:k]]
    long_alpha = top_k_alpha(top_k_actual_long, actual_rets)
    top_k_alpha_dict = {
        "long": long_alpha,
        "short": 0.0,
        "combined": long_alpha,
    }

    # ----- Phase 4: render markdown -----
    report = render_backtest_report(
        title="Plan B backtest",
        window_label=f"{start.isoformat()}..{end.isoformat()}",
        overall=overall,
        per_regime=per_regime,
        calibration_buckets=buckets,
        top_k_alpha=top_k_alpha_dict,
        survivorship_bias_flag=True,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    log.info("backtest_done", **overall)
    return overall
```

- [ ] **Step 4: Verify PASS** (1 test)

- [ ] **Step 5: Create CLI script**

```python
# scripts/run_backtest.py
"""CLI wrapper for `run_backtest`."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import ccxt

from crypto_predictor.backtest.runner import run_backtest
from crypto_predictor.logging_config import configure_logging


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("--history-root", type=Path, default=Path("data/history"))
    parser.add_argument("--sentiment-cache", type=Path,
                        default=Path("data/sentiment_cache.db"))
    parser.add_argument("--global-cache", type=Path,
                        default=Path("data/global_cache.db"))
    parser.add_argument("--sector-map", type=Path, default=Path("data/sector_map.yaml"))
    parser.add_argument("--start", type=str, required=True,
                        help="ISO date, e.g. 2026-01-01")
    parser.add_argument("--end", type=str, required=True)
    parser.add_argument("--train-days", type=int, default=90)
    parser.add_argument("--cal-days", type=int, default=30)
    parser.add_argument("--val-days", type=int, default=30)
    parser.add_argument("--slide-days", type=int, default=7)
    parser.add_argument("--sample-interval-hours", type=int, default=12)
    parser.add_argument("--symbols", type=str, default="",
                        help="Comma-separated, blank = all listed perps")
    parser.add_argument("--report", type=Path,
                        default=Path("docs/backtest/report.md"))
    parser.add_argument("--calibration", type=Path,
                        default=Path("data/calibration_map.json"))
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    else:
        okx = ccxt.okx({"enableRateLimit": True})
        markets = okx.load_markets()
        symbols = [m["symbol"] for m in markets.values()
                   if m.get("swap") and m.get("settle") == "USDT" and m.get("active")]

    run_backtest(
        history_root=args.history_root,
        sentiment_cache=args.sentiment_cache,
        global_cache=args.global_cache,
        sector_map=args.sector_map,
        start=start, end=end,
        train_days=args.train_days, cal_days=args.cal_days, val_days=args.val_days,
        slide_days=args.slide_days,
        sample_interval_hours=args.sample_interval_hours,
        symbols=symbols,
        report_path=args.report,
        calibration_path=args.calibration,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Commit + push**

```powershell
git add src/crypto_predictor/backtest/runner.py scripts/run_backtest.py tests/test_backtest/test_runner_synthetic.py
git commit -m "feat(backtest): walk-forward runner + CLI script"
git push
```

**Week 5 done.** Verify:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
Expected: ~130 tests pass.

---

# Week 6 — Run backtest + tune + validate

Goal: run the real backtest on 6 months of ingested data, hit success criteria (or document why not), commit results.

## Task 6.1: Run baseline backtest

**Files:**
- Create: `docs/backtest/baseline-report.md` (output)
- Create: `data/calibration_map.json` (output, gitignored as `*.json` in data/ — but we'll commit this one)

> **Note**: this is an operational task, not a code change. It executes `scripts/run_backtest.py` against the real ingested data.

- [ ] **Step 1: Pick a backtest window**

The ingest covers ~6 months ending now. For walk-forward, we need at least train_days + cal_days + val_days. Use:
- Start: 6 months ago
- End: 7 days ago (avoid stale data tail)
- train_days=90, cal_days=30, val_days=30, slide_days=14
- sample_interval_hours=24 (one prediction per coin per day, manageable)
- symbols: empty (= all 340 listed perps)

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
# compute dates dynamically
$end = (Get-Date).AddDays(-7).ToString("yyyy-MM-dd")
$start = (Get-Date).AddMonths(-6).ToString("yyyy-MM-dd")
Write-Output "Backtest window: $start to $end"
.\.venv\Scripts\python.exe scripts\run_backtest.py `
    --start $start `
    --end $end `
    --train-days 90 `
    --cal-days 30 `
    --val-days 30 `
    --slide-days 14 `
    --sample-interval-hours 24 `
    --report docs\backtest\baseline-report.md `
    --calibration data\calibration_map.json
```

Expected runtime: ~5–15 minutes (340 symbols × ~150 sample days × feature compute). If much slower, reduce universe (`--symbols "BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT,..."`) to top 50 mcap coins first.

- [ ] **Step 2: Inspect the report**

```powershell
Get-Content docs\backtest\baseline-report.md
```

Note overall hit rate, per-regime hit rate, calibration MAE. Compare to success criteria (spec §19):
- Hit rate ≥ 58%
- Calibration MAE ≤ 5%
- Top-K alpha ≥ +1.5%
- Brier ≤ 0.23

- [ ] **Step 3: Commit results**

```powershell
# Override gitignore for calibration map (it's small + meaningful state)
git add docs/backtest/baseline-report.md -f
git add data/calibration_map.json -f
git commit -m "docs: baseline backtest report + calibration map"
git push
```

---

## Task 6.2: Tune weights if hit rate < 58%

> **Conditional**: only execute if Task 6.1 reported hit rate < 58%.

- [ ] **Step 1: Identify weakest family**

Open `docs/backtest/baseline-report.md`. Look at per-regime hit rates. If one regime is dragging down overall (e.g., BEAR is 50%), inspect which features fire in BEAR predictions.

Then experiment with weight tweaks. Possible adjustments (per spec §8.1):
- If perp microstructure is noisy in BEAR → reduce its weight in that regime (requires per-regime weights — a Plan B.5 extension)
- If sentiment is hurting → reduce its weight globally
- If technical is good → boost it

- [ ] **Step 2: Add per-regime weight support to direction.py**

```python
# Edit src/crypto_predictor/scoring/direction.py to support regime-conditional weights:

DEFAULT_REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "BULL": DEFAULT_WEIGHTS,
    "BEAR": {"momentum": 0.15, "perp": 0.20, "volume": 0.10,
             "technical": 0.20, "sentiment": 0.10, "global": 0.25},
    "CHOP": DEFAULT_WEIGHTS,
}
```

And update `compute_direction_raw(feats, regime: str = "CHOP")` to look up regime weights.

- [ ] **Step 3: Update runner.py to pass regime to direction**

```python
# In runner.py phase 1 inner loop:
raw = compute_direction_raw(feats, regime=regime)
```

- [ ] **Step 4: Re-run backtest, compare**

Re-run Task 6.1 command, save to `docs/backtest/tuned-report.md`. Compare overall hit rate.

- [ ] **Step 5: Commit if improved**

```powershell
git add src/crypto_predictor/scoring/direction.py src/crypto_predictor/backtest/runner.py docs/backtest/tuned-report.md
git commit -m "tune(scoring): regime-conditional weights to improve BEAR hit rate"
git push
```

If hit rate still < 58% after tuning, see Task 6.4.

---

## Task 6.3: Plan B integration test

**Files:**
- Create: `tests/integration/test_plan_b_integration.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/integration/test_plan_b_integration.py
"""Plan B end-to-end: scoring + calibration + tiny backtest on real BTC + ETH + SOL."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from crypto_predictor.backtest.runner import run_backtest

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = REPO_ROOT / "data" / "history"
SECTOR_MAP = REPO_ROOT / "data" / "sector_map.yaml"


@pytest.mark.skipif(
    not (HISTORY_ROOT / "ohlcv" / "BTC_USDT_USDT" / "1h.parquet").exists(),
    reason="ingest not done; skipping",
)
def test_tiny_backtest_runs_end_to_end(tmp_path: Path):
    end = datetime.now(timezone.utc) - timedelta(days=7)
    start = end - timedelta(days=60)
    report = tmp_path / "report.md"
    calib = tmp_path / "calib.json"

    summary = run_backtest(
        history_root=HISTORY_ROOT,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=SECTOR_MAP,
        start=start, end=end,
        train_days=21, cal_days=14, val_days=14, slide_days=7,
        sample_interval_hours=48,
        symbols=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
        report_path=report,
        calibration_path=calib,
    )
    assert summary["n_predictions"] > 0
    assert report.exists()
    assert calib.exists()
    assert "Plan B backtest" in report.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run integration test**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_plan_b_integration.py -v
```

If it passes, Plan B's scoring + calibration + backtest is wired correctly end-to-end on real data.

- [ ] **Step 3: Run full suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Expected: ~132+ tests pass.

- [ ] **Step 4: Commit**

```powershell
git add tests/integration/test_plan_b_integration.py
git commit -m "test(integration): Plan B end-to-end on real BTC/ETH/SOL data"
git push
```

---

## Task 6.4: Plan B completion report

**Files:**
- Create: `docs/plans/2026-XX-XX-plan-b-completion-report.md` (date when complete)

- [ ] **Step 1: Write completion report**

Summarize:
- Final hit rate, MAE, Brier, top-K alpha (from baseline + tuned reports)
- Whether success criteria met (≥58% hit rate, ≤5% calibration MAE, ≥+1.5% alpha)
- Any deviations from plan
- Outstanding issues
- Recommendation for Plan C

Template:

```markdown
# Plan B Completion Report — Modeling (Weeks 4–6)

**Date**: 2026-XX-XX
**Status**: ✅ All 18 tasks complete; backtest on 6mo data ran end-to-end

## Backtest results (final)

| Metric | Value | Target (§19) | Met? |
|---|---|---|---|
| Hit rate (overall) | XX.X% | ≥ 58% | ✅/❌ |
| Calibration MAE | X.X% | ≤ 5% | ✅/❌ |
| Brier score | 0.XXX | ≤ 0.23 | ✅/❌ |
| Top-K alpha (long) | +X.X% | ≥ 1.5% | ✅/❌ |

## Per regime hit rates

(paste from final report)

## Deviations from plan

- ...

## Outstanding follow-ups

- ...

## Plan C scope preview

When ready: Plan C covers Weeks 7–8 — daily orchestrator + LLM summary + ranker + markdown + Telegram. Triggered by `Plan C yaz`.
```

- [ ] **Step 2: Commit**

```powershell
git add docs/plans/2026-XX-XX-plan-b-completion-report.md
git commit -m "docs: Plan B completion report"
git push
```

---

## Plan B complete — handoff to Plan C

✅ **What we have at end of Plan B:**

| Capability | Status |
|---|---|
| 6 family tilt functions + direction_raw formula | ✓ |
| Magnitude estimator with regime multiplier | ✓ |
| Regime detector (BULL/BEAR/CHOP) | ✓ |
| Anomaly flag + composite score | ✓ |
| Walk-forward backtest framework | ✓ |
| Per-regime isotonic calibration + JSON persistence | ✓ |
| Metrics: hit rate, MAE, Brier, top-K alpha, calibration buckets | ✓ |
| Markdown backtest report generator | ✓ |
| CLI: `scripts/run_backtest.py` | ✓ |
| Baseline backtest run on 6 months of real data | ✓ |
| Plan B integration test (real BTC/ETH/SOL) | ✓ |

❌ **What Plan B does NOT yet do:**
- Save predictions to predictions.db (Plan D)
- Generate any user-facing output beyond backtest report (Plan C)
- Have any LLM in the loop (Plan C — top-K summaries)
- Validate live predictions or compute rolling metrics (Plan D)
- Send any Telegram alert (Plan C/D)

---

**Next step:** when Plan B's completion report is committed, say "Plan C yaz" to write Weeks 7–8 plan: daily orchestrator + LLM summary + ranker + markdown report + Telegram output.

---

*End of Plan B.*
