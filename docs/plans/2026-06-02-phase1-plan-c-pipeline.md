# crypto-predictor Phase 1 — Plan C: Daily Pipeline (Weeks 7–8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn Plan B's validated scoring + calibration engine into a daily user-facing product — a 06:00 UTC scan that produces top-K long + top-K short rankings, LLM-narrated, written to a markdown report, and pushed to Telegram with selective high-conviction alerts.

**Architecture:** Two new packages under `src/crypto_predictor/`:
- **`orchestrator/`** — `daily_scan.py` (the main pipeline), `ranker.py` (top-K + wild cards), `llm_summary.py` (Claude Haiku rationale), `universe.py` (symbol + mcap-rank discovery)
- **`output/`** — `markdown_report.py` (§15.1 layout), `telegram_summary.py` (§15.2 compact form), `thresholds.py` (alert routing config)

Plus: wire `scheduler/jobs.py::_job_predict_scan` from a stub into the real pipeline. Reuse the `crypto-intel-hub` Telegram MCP for delivery (no duplication).

**Tech stack:** Same as Plan A/B + `anthropic` SDK for Claude Haiku.

**Related docs:**
- Design spec §5 (architecture), §6 (sentiment strategy), §11 (anomaly), §13 (B loop — partial), §15 (output formats)
- Plan A: data foundation
- Plan B: scoring + calibration (validated, all targets met)
- Phase 1.5 completion: `docs/plans/2026-06-02-phase1.5-completion-report.md`

**Plan C success criteria:**
- `/predict scan` (or scheduled 06:00 UTC) produces a complete markdown report end-to-end in <8 minutes on the full 340-symbol universe
- Markdown matches §15.1 layout: top-20 long, top-20 short, wild cards, calibration track record block
- Telegram summary delivered, fits in one message (~600 chars), matches §15.2
- Selective alerts route based on `thresholds.yaml` (high-conv, wild-card; no spam)
- LLM rationale generated for top-40 candidates only (cost <$0.20/run)
- All Plan C unit + integration tests green; ≥ 25 new tests

---

## Navigation

- **Week 7 — Daily orchestrator + LLM** (8 tasks)
- **Week 8 — Output + Telegram + commands** (6 tasks)
- **Plan C complete — handoff to Plan D**

---

## Prerequisites (before Task 7.1)

- [ ] **Verify Phase 1.5 is complete**

```powershell
cd C:\Users\Koray\Desktop\crypto-predictor
.\.venv\Scripts\python.exe -m pytest -v --tb=short
```
Expected: 137+ tests pass, integration tests pass.

- [ ] **Verify calibration map exists**

```powershell
Test-Path data\calibration_1_5_5.json
Test-Path data\calibration_1_5_4.json
```
Both should be True. We'll point production at `1_5_4.json` (340-symbol fit).

- [ ] **Verify ingest data is fresh enough**

```powershell
.\.venv\Scripts\python.exe scripts\verify_ingest.py --root data\history
```
Stale count should be < 20% of (symbols × timeframes). If significantly higher, run a quick incremental ingest first.

- [ ] **Ensure Anthropic API key is set in `data/secrets.env`**

The `secrets.env` template (Task 1.9) has `ANTHROPIC_API_KEY=` slot. If not filled in, Plan C will skip LLM rationale generation (graceful degradation) but you'll lose the §15.1 "Top signals" narrative.

- [ ] **Ensure Telegram bot is configured**

`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` should already be populated (carried over from crypto-intel-hub setup).

---

# Week 7 — Daily orchestrator + LLM summary

## Task 7.1: Symbol universe + mcap rank discovery

**Files:**
- Create: `src/crypto_predictor/orchestrator/__init__.py`
- Create: `src/crypto_predictor/orchestrator/universe.py`
- Create: `tests/test_orchestrator/__init__.py`
- Create: `tests/test_orchestrator/test_universe.py`

**Purpose:** Discover the current 340-perp universe and assign mcap-rank weights. `mcap_rank_weight` from Plan A needs the rank as input.

- [ ] Step 1: Failing test

```python
# tests/test_orchestrator/test_universe.py
from unittest.mock import MagicMock

from crypto_predictor.orchestrator.universe import (
    list_active_perps, assign_mcap_ranks,
)


def test_list_active_perps_filters_usdt_settled():
    fake = MagicMock()
    fake.load_markets.return_value = {
        "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "swap": True,
                          "settle": "USDT", "active": True},
        "ETH/USD:USD": {"symbol": "ETH/USD:USD", "swap": True,
                        "settle": "USD", "active": True},  # not USDT
        "BTC/USDT": {"symbol": "BTC/USDT", "swap": False,
                     "settle": "USDT", "active": True},  # spot
        "DEAD/USDT:USDT": {"symbol": "DEAD/USDT:USDT", "swap": True,
                           "settle": "USDT", "active": False},  # delisted
    }
    symbols = list_active_perps(fake)
    assert "BTC/USDT:USDT" in symbols
    assert "ETH/USD:USD" not in symbols
    assert "BTC/USDT" not in symbols
    assert "DEAD/USDT:USDT" not in symbols


def test_assign_mcap_ranks_from_dict():
    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "ZZZ/USDT:USDT"]
    mcap_map = {"BTC": 1, "ETH": 2}  # ZZZ unknown
    ranks = assign_mcap_ranks(symbols, mcap_map)
    assert ranks["BTC/USDT:USDT"] == 1
    assert ranks["ETH/USDT:USDT"] == 2
    assert ranks["ZZZ/USDT:USDT"] is None
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/orchestrator/__init__.py
"""Daily orchestrator — discovery, scan, rank, narrate."""
```

```python
# src/crypto_predictor/orchestrator/universe.py
"""Symbol universe + mcap-rank discovery."""
from __future__ import annotations

from crypto_predictor.data.okx_client import ccxt_to_base_ccy


def list_active_perps(ccxt_client) -> list[str]:
    """Return list of active USDT-settled perpetual symbols on OKX."""
    markets = ccxt_client.load_markets()
    return [
        m["symbol"] for m in markets.values()
        if m.get("swap") and m.get("settle") == "USDT" and m.get("active")
    ]


def assign_mcap_ranks(symbols: list[str],
                      mcap_map: dict[str, int]) -> dict[str, int | None]:
    """Map each symbol to a mcap rank, or None if unknown."""
    out: dict[str, int | None] = {}
    for sym in symbols:
        base = ccxt_to_base_ccy(sym)
        out[sym] = mcap_map.get(base)
    return out
```

- [ ] Step 4: Verify PASS (2 tests)

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/orchestrator/ tests/test_orchestrator/
git commit -m "feat(orchestrator): universe discovery + mcap-rank assignment"
git push
```

---

## Task 7.2: Daily-scan orchestrator skeleton

**Files:**
- Create: `src/crypto_predictor/orchestrator/daily_scan.py`
- Create: `tests/test_orchestrator/test_daily_scan_synthetic.py`

**Purpose:** Core pipeline that, for each coin: compute_features → compute_direction_raw_for_regime → predict_probability → compute_expected_return → is_anomalous → composite_score. Save all predictions to `predictions.db`.

- [ ] Step 1: Failing test

```python
# tests/test_orchestrator/test_daily_scan_synthetic.py
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.orchestrator.daily_scan import run_daily_scan
from crypto_predictor.storage.predictions_db import init_db as init_predictions_db


def _seed(root: Path, n_symbols: int = 3):
    np.random.seed(0)
    for i in range(n_symbols):
        sym = f"FAKE{i}/USDT:USDT"
        p = 100.0
        rows = []
        for h in range(2500):
            p *= np.exp(np.random.normal(0.0, 0.005))
            rows.append({
                "timestamp": 1700000000000 + h * 3600 * 1000,
                "open": p, "high": p * 1.01, "low": p * 0.99,
                "close": p, "volume": 1000,
            })
        write_ohlcv(root, sym, "1h", pd.DataFrame(rows))
        for tf, step in [("15m", 900), ("4h", 14400), ("1d", 86400)]:
            n = max(120, 100 * (86400 // step) if step <= 86400 else 100)
            n = min(n, 8800)
            df = pd.DataFrame([
                {"timestamp": 1700000000000 + j * step * 1000, "open": 100,
                 "high": 101, "low": 99, "close": 100, "volume": 1000}
                for j in range(n)
            ])
            write_ohlcv(root, sym, tf, df)
        for kind in ["funding", "oi", "ls_ratio", "liq"]:
            p_path = parquet_path(root, sym, kind, "futures")
            p_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame().to_parquet(p_path, index=False)


def test_run_daily_scan_persists_predictions(tmp_path: Path):
    history = tmp_path / "history"
    _seed(history, n_symbols=3)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("l1:\n" + "\n".join(
        f"  - FAKE{i}/USDT:USDT" for i in range(3)
    ) + "\n")
    db = tmp_path / "predictions.db"
    init_predictions_db(db)

    asof = datetime.fromtimestamp(
        (1700000000000 + 2400 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    result = run_daily_scan(
        history_root=history,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=sector_map,
        predictions_db=db,
        calibration_path=None,  # use default 0.5 fallback
        symbols=[f"FAKE{i}/USDT:USDT" for i in range(3)],
        mcap_ranks={f"FAKE{i}/USDT:USDT": 1 for i in range(3)},
        asof=asof,
        formula_version="v1.5",
        global_mcap_trend=0.0,
    )

    assert result["n_predictions"] == 3
    assert result["regime"] in ("BULL", "BEAR", "CHOP")

    # Predictions persisted
    import sqlite3
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT symbol, prediction, p_direction, target_value, "
        "       composite_score, confidence_flag, regime, status "
        "FROM predictions"
    ).fetchall()
    conn.close()
    assert len(rows) == 3
    for row in rows:
        symbol, prediction, p_direction, target_value, composite, flag, regime, status = row
        assert prediction in ("up", "down")
        assert 0.0 <= p_direction <= 1.0
        assert flag in ("NORMAL", "HIGH_CONV", "WILD_CARD")
        assert status == "pending"
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/orchestrator/daily_scan.py
"""Daily prediction pipeline: features → scoring → calibration → persistence."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import structlog

from crypto_predictor.calibration.isotonic import (
    RegimeCalibrators, predict_probability,
)
from crypto_predictor.calibration.persistence import load_calibration
from crypto_predictor.features.compute import compute_features
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.scoring.anomaly import is_anomalous
from crypto_predictor.scoring.composite import compute_composite
from crypto_predictor.scoring.direction import compute_direction_raw_for_regime
from crypto_predictor.scoring.magnitude import compute_expected_return
from crypto_predictor.scoring.regime import detect_regime

log = structlog.get_logger(__name__)


def _classify_flag(p_direction: float, expected_return: float, anomalous: bool,
                   high_conv_p: float = 0.78,
                   high_conv_ret: float = 0.04) -> str:
    if anomalous:
        return "WILD_CARD"
    if p_direction > high_conv_p and abs(expected_return) > high_conv_ret:
        return "HIGH_CONV"
    return "NORMAL"


def run_daily_scan(*, history_root: Path,
                   sentiment_cache: Path, global_cache: Path,
                   sector_map: Path,
                   predictions_db: Path,
                   calibration_path: Path | None,
                   symbols: list[str],
                   mcap_ranks: dict[str, int | None],
                   asof: datetime,
                   formula_version: str,
                   global_mcap_trend: float = 0.0,
                   horizon_hours: int = 24) -> dict:
    """Run the daily scan: predict for every symbol, persist to predictions.db."""
    log.info("daily_scan_start", asof=asof.isoformat(), n_symbols=len(symbols))

    calibs = load_calibration(calibration_path) if calibration_path else RegimeCalibrators()
    calibration_version = calibration_path.stem if calibration_path else "uncalibrated"

    fetcher = FeatureFetcher(root=history_root, asof=asof)
    regime = detect_regime(fetcher, global_mcap_trend=global_mcap_trend)
    log.info("daily_scan_regime", regime=regime)

    conn = sqlite3.connect(str(predictions_db))
    try:
        n_predictions = 0
        n_skipped = 0
        for sym in symbols:
            try:
                feats = compute_features(
                    fetcher=fetcher, symbol=sym,
                    sentiment_cache=sentiment_cache, global_cache=global_cache,
                    sector_map_path=sector_map,
                    mcap_rank=mcap_ranks.get(sym),
                )
            except Exception as exc:
                log.warning("feature_compute_failed", symbol=sym, error=str(exc))
                n_skipped += 1
                continue

            raw = compute_direction_raw_for_regime(feats, regime)
            p_up = predict_probability(calibs, raw_score=raw, regime=regime)
            expected_ret = compute_expected_return(
                fetcher, sym, direction_raw=raw, regime=regime
            )
            anomalous = is_anomalous(feats)
            prediction = "up" if p_up >= 0.5 else "down"
            p_direction = p_up if prediction == "up" else (1.0 - p_up)
            composite = compute_composite(
                p_up=p_up, expected_return=expected_ret, anomalous=anomalous
            )
            flag = _classify_flag(p_direction, expected_ret, anomalous)

            pred_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO predictions ("
                "id, symbol, horizon_hours, prediction, p_direction, target_value, "
                "composite_score, confidence_flag, regime, formula_version, "
                "calibration_version, status, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (pred_id, sym, horizon_hours, prediction, p_direction, expected_ret,
                 composite, flag, regime, formula_version,
                 calibration_version, asof.isoformat()),
            )
            n_predictions += 1
        conn.commit()
    finally:
        conn.close()

    log.info("daily_scan_done", n_predictions=n_predictions, n_skipped=n_skipped)
    return {
        "asof": asof.isoformat(),
        "regime": regime,
        "n_predictions": n_predictions,
        "n_skipped": n_skipped,
    }
```

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/orchestrator/daily_scan.py tests/test_orchestrator/test_daily_scan_synthetic.py
git commit -m "feat(orchestrator): daily_scan pipeline persists predictions to predictions.db"
git push
```

---

## Task 7.3: Ranker — top-K long + top-K short + wild cards

**Files:**
- Create: `src/crypto_predictor/orchestrator/ranker.py`
- Create: `tests/test_orchestrator/test_ranker.py`

- [ ] Step 1: Failing test

```python
# tests/test_orchestrator/test_ranker.py
from crypto_predictor.orchestrator.ranker import rank_predictions, RankedSlate


def test_rank_predictions_separates_long_short_wild():
    rows = [
        # high-conviction longs
        {"id": "a", "symbol": "SOL", "prediction": "up", "p_direction": 0.82,
         "target_value": 0.06, "composite_score": 0.049, "confidence_flag": "HIGH_CONV"},
        {"id": "b", "symbol": "AVAX", "prediction": "up", "p_direction": 0.76,
         "target_value": 0.05, "composite_score": 0.038, "confidence_flag": "NORMAL"},
        # normal short
        {"id": "c", "symbol": "ENS", "prediction": "down", "p_direction": 0.72,
         "target_value": -0.04, "composite_score": 0.029, "confidence_flag": "NORMAL"},
        # wild card
        {"id": "d", "symbol": "AGIX", "prediction": "up", "p_direction": 0.81,
         "target_value": 0.07, "composite_score": 0.040, "confidence_flag": "WILD_CARD"},
    ]
    slate = rank_predictions(rows, k_long=10, k_short=10)
    assert isinstance(slate, RankedSlate)
    assert "SOL" in [p["symbol"] for p in slate.top_long]
    assert "ENS" in [p["symbol"] for p in slate.top_short]
    # Wild card excluded from top-K, in its own list
    assert "AGIX" in [p["symbol"] for p in slate.wild_cards]
    assert "AGIX" not in [p["symbol"] for p in slate.top_long]


def test_rank_predictions_orders_by_composite_descending():
    rows = [
        {"id": "a", "symbol": "A", "prediction": "up", "p_direction": 0.7,
         "target_value": 0.04, "composite_score": 0.028, "confidence_flag": "NORMAL"},
        {"id": "b", "symbol": "B", "prediction": "up", "p_direction": 0.6,
         "target_value": 0.08, "composite_score": 0.048, "confidence_flag": "NORMAL"},
        {"id": "c", "symbol": "C", "prediction": "up", "p_direction": 0.8,
         "target_value": 0.02, "composite_score": 0.016, "confidence_flag": "NORMAL"},
    ]
    slate = rank_predictions(rows, k_long=10, k_short=10)
    # Ordered by composite_score desc: B (0.048), A (0.028), C (0.016)
    symbols = [p["symbol"] for p in slate.top_long]
    assert symbols == ["B", "A", "C"]
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/orchestrator/ranker.py
"""Top-K ranking — separate long, short, wild-card slates."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RankedSlate:
    top_long: list[dict] = field(default_factory=list)
    top_short: list[dict] = field(default_factory=list)
    wild_cards: list[dict] = field(default_factory=list)


def rank_predictions(predictions: list[dict],
                     k_long: int = 20, k_short: int = 20) -> RankedSlate:
    """Split predictions into long top-K, short top-K, and wild cards.

    Wild cards are excluded from top-K and go into their own bucket.
    """
    wild = [p for p in predictions if p["confidence_flag"] == "WILD_CARD"]
    normal = [p for p in predictions if p["confidence_flag"] != "WILD_CARD"]

    longs = sorted(
        [p for p in normal if p["prediction"] == "up"],
        key=lambda p: p["composite_score"], reverse=True,
    )[:k_long]
    shorts = sorted(
        [p for p in normal if p["prediction"] == "down"],
        key=lambda p: p["composite_score"], reverse=True,
    )[:k_short]
    wild_sorted = sorted(wild, key=lambda p: p["composite_score"], reverse=True)

    return RankedSlate(top_long=longs, top_short=shorts, wild_cards=wild_sorted)
```

- [ ] Step 4: Verify PASS (2 tests)

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/orchestrator/ranker.py tests/test_orchestrator/test_ranker.py
git commit -m "feat(orchestrator): ranker — top-K long/short + wild cards (anomaly-aware)"
git push
```

---

## Task 7.4: LLM rationale generator (Claude Haiku)

**Files:**
- Create: `src/crypto_predictor/orchestrator/llm_summary.py`
- Create: `tests/test_orchestrator/test_llm_summary.py`

**Purpose:** For top-40 candidates, generate a 2–3 sentence rationale grounded in the top-3 feature values. Use `anthropic` SDK with `claude-haiku-4-5`. Graceful degradation if API key missing.

- [ ] Step 1: Failing test

```python
# tests/test_orchestrator/test_llm_summary.py
from unittest.mock import MagicMock, patch

from crypto_predictor.orchestrator.llm_summary import (
    generate_rationale, summarize_top_signals,
)


def test_summarize_top_signals_picks_three_highest_abs():
    feats = {
        "ret_24h_z": 0.5, "funding_z": -2.3, "rsi_14_1h": 60,
        "oi_growth_z": 1.5, "vol_z_24h": 0.1,
    }
    top = summarize_top_signals(feats, n=3)
    # Top 3 by abs value: funding_z (-2.3), oi_growth_z (1.5), ret_24h_z (0.5)
    names = [t[0] for t in top]
    assert "funding_z" in names
    assert "oi_growth_z" in names
    assert "ret_24h_z" in names


def test_generate_rationale_returns_string_with_mock_llm(monkeypatch):
    fake_client = MagicMock()
    fake_message = MagicMock()
    fake_message.content = [MagicMock(text="Funding extreme negative; OI rising; momentum supportive.")]
    fake_client.messages.create.return_value = fake_message
    summary = generate_rationale(
        client=fake_client,
        symbol="BTC/USDT:USDT",
        prediction="up",
        p_direction=0.78,
        expected_return=0.05,
        top_signals=[("funding_z", -2.3), ("oi_growth_z", 1.5), ("ret_24h_z", 0.5)],
    )
    assert isinstance(summary, str)
    assert len(summary) > 10


def test_generate_rationale_returns_fallback_when_client_none():
    summary = generate_rationale(
        client=None,
        symbol="BTC/USDT:USDT",
        prediction="up",
        p_direction=0.78,
        expected_return=0.05,
        top_signals=[("funding_z", -2.3), ("oi_growth_z", 1.5), ("ret_24h_z", 0.5)],
    )
    assert "funding_z" in summary  # fallback shows raw signals
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/orchestrator/llm_summary.py
"""LLM rationale generator using Claude Haiku."""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

MODEL = "claude-haiku-4-5"


def summarize_top_signals(feats: dict, n: int = 3) -> list[tuple[str, float]]:
    """Pick the n features with the highest |value| from the feats dict.

    Excludes meta features like mcap_rank_weight.
    """
    excluded = {"mcap_rank_weight", "coin_btc_corr_30d"}
    candidates = [
        (name, float(v)) for name, v in feats.items()
        if name not in excluded and v is not None
    ]
    candidates.sort(key=lambda x: abs(x[1]), reverse=True)
    return candidates[:n]


def _fallback_rationale(symbol: str, prediction: str, p_direction: float,
                        expected_return: float,
                        top_signals: list[tuple[str, float]]) -> str:
    parts = ", ".join(f"{name}={value:+.2f}" for name, value in top_signals)
    direction = "↑" if prediction == "up" else "↓"
    return (f"{symbol} {direction} P={p_direction:.2f} target={expected_return:+.2%}. "
            f"Signals: {parts}")


def generate_rationale(*, client,
                       symbol: str, prediction: str, p_direction: float,
                       expected_return: float,
                       top_signals: list[tuple[str, float]]) -> str:
    """Generate a 2-3 sentence rationale via Claude Haiku. Falls back to a
    structured one-liner if client is None or API fails.
    """
    if client is None:
        return _fallback_rationale(symbol, prediction, p_direction,
                                    expected_return, top_signals)

    signal_lines = "\n".join(
        f"- {name}: {value:+.2f}" for name, value in top_signals
    )
    prompt = (
        f"You are summarizing a crypto trading signal in 2-3 sentences. "
        f"Coin: {symbol}. Prediction: {prediction}. "
        f"Calibrated probability: {p_direction:.2f}. "
        f"Expected 24h return: {expected_return:+.2%}.\n\n"
        f"Top supporting signals (z-scored or raw):\n{signal_lines}\n\n"
        f"Write a tight rationale grounded in the signals above. Don't invent. "
        f"No disclaimers. No more than 60 words."
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else ""
        return text.strip() or _fallback_rationale(
            symbol, prediction, p_direction, expected_return, top_signals,
        )
    except Exception as exc:
        log.warning("llm_rationale_failed", symbol=symbol, error=str(exc))
        return _fallback_rationale(
            symbol, prediction, p_direction, expected_return, top_signals,
        )
```

- [ ] Step 4: Verify PASS (3 tests)

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/orchestrator/llm_summary.py tests/test_orchestrator/test_llm_summary.py
git commit -m "feat(orchestrator): Claude Haiku rationale generator with safe fallback"
git push
```

---

## Task 7.5: Universe-wide daily run end-to-end

**Files:**
- Create: `src/crypto_predictor/orchestrator/run.py`  (single entry point composing 7.1–7.4 + ranker)
- Create: `tests/test_orchestrator/test_run_end_to_end.py`

- [ ] Step 1: Failing test

```python
# tests/test_orchestrator/test_run_end_to_end.py
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path, write_ohlcv
from crypto_predictor.orchestrator.run import run_full_scan
from crypto_predictor.storage.predictions_db import init_db as init_predictions_db


def _seed_universe(root: Path, n: int = 4):
    np.random.seed(1)
    for i in range(n):
        sym = f"COIN{i}/USDT:USDT"
        p = 100.0
        rows = []
        for h in range(2500):
            p *= np.exp(np.random.normal(0.0, 0.005))
            rows.append({"timestamp": 1700000000000 + h * 3600 * 1000,
                         "open": p, "high": p * 1.01, "low": p * 0.99,
                         "close": p, "volume": 1000})
        write_ohlcv(root, sym, "1h", pd.DataFrame(rows))
        for tf, step in [("15m", 900), ("4h", 14400), ("1d", 86400)]:
            n_bars = max(120, 100 * (86400 // step) if step <= 86400 else 100)
            n_bars = min(n_bars, 8800)
            df = pd.DataFrame([
                {"timestamp": 1700000000000 + j * step * 1000, "open": 100,
                 "high": 101, "low": 99, "close": 100, "volume": 1000}
                for j in range(n_bars)
            ])
            write_ohlcv(root, sym, tf, df)
        for kind in ["funding", "oi", "ls_ratio", "liq"]:
            p_path = parquet_path(root, sym, kind, "futures")
            p_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame().to_parquet(p_path, index=False)


def test_run_full_scan_produces_ranked_slate_and_persists(tmp_path: Path):
    history = tmp_path / "history"
    _seed_universe(history, n=4)
    sector_map = tmp_path / "sector_map.yaml"
    sector_map.write_text("l1:\n" + "\n".join(
        f"  - COIN{i}/USDT:USDT" for i in range(4)
    ) + "\n")
    db = tmp_path / "predictions.db"
    init_predictions_db(db)

    asof = datetime.fromtimestamp(
        (1700000000000 + 2400 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    result = run_full_scan(
        history_root=history,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=sector_map,
        predictions_db=db,
        calibration_path=None,
        symbols=[f"COIN{i}/USDT:USDT" for i in range(4)],
        mcap_ranks={f"COIN{i}/USDT:USDT": 1 for i in range(4)},
        asof=asof,
        formula_version="v1.5",
        k_long=2, k_short=2,
        llm_client=None,
    )

    assert result["scan"]["n_predictions"] == 4
    slate = result["slate"]
    assert hasattr(slate, "top_long")
    assert hasattr(slate, "top_short")
    assert hasattr(slate, "wild_cards")
    # Each long/short entry has rationale text
    for entry in slate.top_long + slate.top_short:
        assert "rationale" in entry
        assert isinstance(entry["rationale"], str)
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/orchestrator/run.py
"""Daily run composing scan + rank + LLM narrative."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import structlog

from crypto_predictor.features.compute import compute_features
from crypto_predictor.features.fetcher import FeatureFetcher
from crypto_predictor.orchestrator.daily_scan import run_daily_scan
from crypto_predictor.orchestrator.llm_summary import (
    generate_rationale, summarize_top_signals,
)
from crypto_predictor.orchestrator.ranker import rank_predictions, RankedSlate

log = structlog.get_logger(__name__)


def _narrate_slate(slate: RankedSlate, *, fetcher: FeatureFetcher,
                   sentiment_cache: Path, global_cache: Path,
                   sector_map: Path, mcap_ranks: dict[str, int | None],
                   llm_client) -> None:
    """Add a 'rationale' field to each prediction in the slate using LLM (or fallback)."""
    candidates = slate.top_long + slate.top_short + slate.wild_cards
    for entry in candidates:
        sym = entry["symbol"]
        try:
            feats = compute_features(
                fetcher=fetcher, symbol=sym,
                sentiment_cache=sentiment_cache, global_cache=global_cache,
                sector_map_path=sector_map,
                mcap_rank=mcap_ranks.get(sym),
            )
        except Exception:
            entry["rationale"] = "(features unavailable)"
            continue
        top_signals = summarize_top_signals(feats, n=3)
        entry["rationale"] = generate_rationale(
            client=llm_client,
            symbol=sym, prediction=entry["prediction"],
            p_direction=entry["p_direction"],
            expected_return=entry["target_value"],
            top_signals=top_signals,
        )


def _load_predictions(db: Path, asof: datetime) -> list[dict]:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT id, symbol, prediction, p_direction, target_value, "
            "       composite_score, confidence_flag, regime "
            "FROM predictions WHERE created_at = ?",
            (asof.isoformat(),),
        ).fetchall()
    finally:
        conn.close()
    cols = ["id", "symbol", "prediction", "p_direction", "target_value",
            "composite_score", "confidence_flag", "regime"]
    return [dict(zip(cols, r)) for r in rows]


def run_full_scan(*, history_root: Path,
                  sentiment_cache: Path, global_cache: Path,
                  sector_map: Path, predictions_db: Path,
                  calibration_path: Path | None,
                  symbols: list[str],
                  mcap_ranks: dict[str, int | None],
                  asof: datetime,
                  formula_version: str,
                  global_mcap_trend: float = 0.0,
                  k_long: int = 20, k_short: int = 20,
                  llm_client=None) -> dict:
    """End-to-end daily scan: predict + persist + rank + narrate."""
    scan = run_daily_scan(
        history_root=history_root,
        sentiment_cache=sentiment_cache, global_cache=global_cache,
        sector_map=sector_map, predictions_db=predictions_db,
        calibration_path=calibration_path,
        symbols=symbols, mcap_ranks=mcap_ranks,
        asof=asof, formula_version=formula_version,
        global_mcap_trend=global_mcap_trend,
    )

    rows = _load_predictions(predictions_db, asof)
    slate = rank_predictions(rows, k_long=k_long, k_short=k_short)

    fetcher = FeatureFetcher(root=history_root, asof=asof)
    _narrate_slate(slate, fetcher=fetcher,
                   sentiment_cache=sentiment_cache, global_cache=global_cache,
                   sector_map=sector_map, mcap_ranks=mcap_ranks,
                   llm_client=llm_client)

    return {"scan": scan, "slate": slate}
```

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/orchestrator/run.py tests/test_orchestrator/test_run_end_to_end.py
git commit -m "feat(orchestrator): run_full_scan composes scan + rank + LLM narrate"
git push
```

---

## Task 7.6: Wire scheduler `predict_scan` job

**Files:**
- Modify: `src/crypto_predictor/scheduler/jobs.py` (replace no-op stub)
- Create: `tests/test_scheduler/test_predict_scan_job.py`

- [ ] Step 1: Failing test

```python
# tests/test_scheduler/test_predict_scan_job.py
from unittest.mock import MagicMock, patch

from crypto_predictor.scheduler.jobs import _job_predict_scan


@patch("crypto_predictor.scheduler.jobs.run_full_scan")
def test_predict_scan_job_calls_orchestrator(mock_run):
    mock_run.return_value = {"scan": {"n_predictions": 5}, "slate": MagicMock()}
    _job_predict_scan()  # should not raise
    mock_run.assert_called_once()
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Replace `_job_predict_scan` in `src/crypto_predictor/scheduler/jobs.py`

Find the existing function:
```python
def _job_predict_scan() -> None:
    log.info("predict_scan job fired (no-op in Plan A)")
```

Replace with a real implementation that loads config from env / defaults and calls `run_full_scan`. Add necessary imports:

```python
import os
from datetime import datetime, timezone
from pathlib import Path

# (add at top of file, with existing imports)

def _job_predict_scan() -> None:
    """Fire the daily prediction scan (06:00 UTC)."""
    from crypto_predictor.orchestrator.run import run_full_scan
    from crypto_predictor.orchestrator.universe import list_active_perps, assign_mcap_ranks
    import ccxt, yaml

    log.info("predict_scan_start")

    project_root = Path(os.environ.get("CRYPTO_PREDICTOR_ROOT",
                                       Path(__file__).resolve().parents[3]))
    history_root = project_root / "data" / "history"
    predictions_db = project_root / "predictions.db"
    sector_map = project_root / "data" / "sector_map.yaml"
    sentiment_cache = project_root / "data" / "sentiment_cache.db"
    global_cache = project_root / "data" / "global_cache.db"
    calibration_path = project_root / "data" / "calibration_1_5_4.json"

    okx = ccxt.okx({"enableRateLimit": True})
    symbols = list_active_perps(okx)

    # Mcap ranks: hardcoded top-100 from data/mcap_ranks.yaml if available, else None
    mcap_ranks_path = project_root / "data" / "mcap_ranks.yaml"
    if mcap_ranks_path.exists():
        mcap_map = yaml.safe_load(mcap_ranks_path.read_text(encoding="utf-8")) or {}
    else:
        mcap_map = {}
    mcap_ranks = assign_mcap_ranks(symbols, mcap_map)

    # Optional LLM client
    llm_client = None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            from anthropic import Anthropic
            llm_client = Anthropic(api_key=api_key)
        except ImportError:
            log.warning("anthropic_sdk_not_installed; rationale will use fallback")

    result = run_full_scan(
        history_root=history_root,
        sentiment_cache=sentiment_cache,
        global_cache=global_cache,
        sector_map=sector_map,
        predictions_db=predictions_db,
        calibration_path=calibration_path,
        symbols=symbols,
        mcap_ranks=mcap_ranks,
        asof=datetime.now(timezone.utc),
        formula_version="v1.5",
        llm_client=llm_client,
    )
    log.info("predict_scan_done",
             n_predictions=result["scan"]["n_predictions"])
```

Also add `anthropic` to `pyproject.toml` deps if not present (it's optional — `try: from anthropic import Anthropic` handles missing gracefully).

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/scheduler/jobs.py tests/test_scheduler/test_predict_scan_job.py
git commit -m "feat(scheduler): wire predict_scan job to run_full_scan with full universe"
git push
```

---

## Task 7.7: `/predict-scan` slash command

**Files:**
- Create: `commands/predict-scan.md`
- Create: `scripts/predict_scan_cli.py` (optional but useful for non-slash testing)

- [ ] Step 1: Create slash command markdown

```markdown
# commands/predict-scan.md
---
description: Run the full daily prediction scan now (universe-wide, ~5-8 min)
---

Run `python scripts/predict_scan_cli.py` and report the slate inline in chat.

Read the latest predictions saved to predictions.db at the asof timestamp,
group by long/short/wild-card, and present the top-5 in each bucket with
rationale.
```

- [ ] Step 2: Create CLI script

```python
# scripts/predict_scan_cli.py
"""On-demand wrapper around the predict_scan scheduler job."""
from __future__ import annotations

import sys

from crypto_predictor.logging_config import configure_logging
from crypto_predictor.scheduler.jobs import _job_predict_scan


def main() -> int:
    configure_logging()
    _job_predict_scan()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Step 3: Commit + push

```powershell
git add commands/predict-scan.md scripts/predict_scan_cli.py
git commit -m "feat(cli): /predict-scan command + standalone CLI wrapper"
git push
```

---

## Task 7.8: Plan C Week-7 dry run on 10 real symbols

This is an operational sanity check, not a code change.

- [ ] Step 1: Run the orchestrator on a small real-data slice

```powershell
$env:CRYPTO_PREDICTOR_ROOT = "C:\Users\Koray\Desktop\crypto-predictor"
.\.venv\Scripts\python.exe -c "
from datetime import datetime, timezone
from pathlib import Path
from crypto_predictor.orchestrator.run import run_full_scan
from crypto_predictor.storage.predictions_db import init_db
root = Path(r'C:\Users\Koray\Desktop\crypto-predictor')
db = root / 'predictions.db'
init_db(db)
symbols = ['BTC/USDT:USDT','ETH/USDT:USDT','SOL/USDT:USDT','BNB/USDT:USDT','XRP/USDT:USDT',
           'DOGE/USDT:USDT','ADA/USDT:USDT','AVAX/USDT:USDT','LINK/USDT:USDT','DOT/USDT:USDT']
mcap_ranks = {s: i+1 for i, s in enumerate(symbols)}
result = run_full_scan(
    history_root=root / 'data' / 'history',
    sentiment_cache=root / 'data' / 'sentiment_cache.db',
    global_cache=root / 'data' / 'global_cache.db',
    sector_map=root / 'data' / 'sector_map.yaml',
    predictions_db=db,
    calibration_path=root / 'data' / 'calibration_1_5_4.json',
    symbols=symbols, mcap_ranks=mcap_ranks,
    asof=datetime.now(timezone.utc),
    formula_version='v1.5',
    k_long=5, k_short=5, llm_client=None,
)
print('Regime:', result['scan']['regime'])
print('n_pred:', result['scan']['n_predictions'])
print()
print('TOP LONGS:')
for p in result['slate'].top_long:
    print(f\"  {p['symbol']} P{p['p_direction']:.2f} ret{p['target_value']:+.2%} -- {p.get('rationale','')[:80]}\")
print()
print('TOP SHORTS:')
for p in result['slate'].top_short:
    print(f\"  {p['symbol']} P{p['p_direction']:.2f} ret{p['target_value']:+.2%} -- {p.get('rationale','')[:80]}\")
"
```

- [ ] Step 2: Visually inspect — do the rationales look right? Are the rankings reasonable? Does the calibration produce a reasonable spread of probabilities?

- [ ] Step 3: If everything looks sensible, commit nothing (this was just a manual check). If something is broken, note the issue and fix in a follow-up task.

---

# Week 8 — Output formatters + Telegram + commands

## Task 8.1: Markdown daily report renderer

**Files:**
- Create: `src/crypto_predictor/output/__init__.py`
- Create: `src/crypto_predictor/output/markdown_report.py`
- Create: `tests/test_output/__init__.py`
- Create: `tests/test_output/test_markdown_report.py`

**Purpose:** Render the slate + rolling metrics into the §15.1 format.

- [ ] Step 1: Failing test

```python
# tests/test_output/test_markdown_report.py
from datetime import datetime, timezone

from crypto_predictor.orchestrator.ranker import RankedSlate
from crypto_predictor.output.markdown_report import render_daily_report


def test_render_daily_report_includes_all_sections():
    slate = RankedSlate(
        top_long=[{"symbol": "SOL/USDT:USDT", "p_direction": 0.78,
                   "target_value": 0.05, "composite_score": 0.039,
                   "rationale": "Funding negative, OI rising."}],
        top_short=[{"symbol": "ENS/USDT:USDT", "p_direction": 0.71,
                    "target_value": -0.04, "composite_score": 0.028,
                    "rationale": "Crowded longs, liq cascade."}],
        wild_cards=[{"symbol": "AGIX/USDT:USDT", "p_direction": 0.81,
                     "target_value": 0.07, "composite_score": 0.040,
                     "rationale": "OI +340% — unprecedented."}],
    )
    md = render_daily_report(
        asof=datetime(2026, 6, 2, 6, 0, tzinfo=timezone.utc),
        regime="BULL",
        slate=slate,
        n_scanned=340, n_skipped=13,
        rolling_metrics={"7d": {"hit_rate": 0.641, "n": 280, "alpha": 0.0312},
                         "30d": {"hit_rate": 0.625, "n": 1200, "alpha": 0.0242}},
    )
    assert "Crypto Predictor — Daily Report" in md
    assert "2026-06-02 06:00 UTC" in md
    assert "Regime: **BULL**" in md
    assert "SOL/USDT:USDT" in md
    assert "ENS/USDT:USDT" in md
    assert "AGIX/USDT:USDT" in md
    assert "Wild Cards" in md
    assert "Validation Track Record" in md
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/output/__init__.py
"""Output formatters — markdown reports + Telegram summaries."""
```

```python
# src/crypto_predictor/output/markdown_report.py
"""Daily markdown report renderer (§15.1)."""
from __future__ import annotations

from datetime import datetime

from crypto_predictor.orchestrator.ranker import RankedSlate


def _row(idx: int, p: dict) -> str:
    return (
        f"| {idx} | {p['symbol']} | "
        f"{p['p_direction']:.2f} | "
        f"{p['target_value']:+.2%} | "
        f"{p['composite_score']:.3f} | "
        f"{p.get('rationale', '')[:120]} |"
    )


def render_daily_report(*, asof: datetime, regime: str, slate: RankedSlate,
                        n_scanned: int, n_skipped: int,
                        rolling_metrics: dict[str, dict]) -> str:
    lines = [
        f"# Crypto Predictor — Daily Report",
        f"**{asof.strftime('%Y-%m-%d %H:%M UTC')}** | Regime: **{regime}** | "
        f"Universe: ~340 OKX Global USDT-Perp",
        "",
        "## Summary",
        f"- Scanned: {n_scanned} coins ({n_scanned - n_skipped} successful, "
        f"{n_skipped} skipped — data freshness)",
        f"- Top {len(slate.top_long)} long candidates, "
        f"top {len(slate.top_short)} short candidates, "
        f"{len(slate.wild_cards)} wild cards",
        "",
        "## 📈 Top Long Candidates",
        "",
        "| # | Coin | P↑ | Exp.Ret | Composite | Rationale |",
        "|---|---|---|---|---|---|",
    ]
    for i, p in enumerate(slate.top_long, start=1):
        lines.append(_row(i, p))
    lines.append("")

    lines += [
        "## 📉 Top Short Candidates",
        "",
        "| # | Coin | P↓ | Exp.Ret | Composite | Rationale |",
        "|---|---|---|---|---|---|",
    ]
    for i, p in enumerate(slate.top_short, start=1):
        lines.append(_row(i, p))
    lines.append("")

    if slate.wild_cards:
        lines += ["## 🃏 Wild Cards (anomaly, handle with caution)", ""]
        for p in slate.wild_cards:
            lines.append(
                f"- **{p['symbol']}** P={p['p_direction']:.2f} "
                f"ret={p['target_value']:+.2%} — {p.get('rationale', '')[:140]}"
            )
        lines.append("")

    if rolling_metrics:
        lines += [
            "## 📊 Validation Track Record (Rolling Windows)",
            "",
            "| Window | Hit Rate | n | Top-K Alpha |",
            "|--------|---------|---|-------------|",
        ]
        for win, m in rolling_metrics.items():
            lines.append(
                f"| {win} | {m['hit_rate']*100:.1f}% | {m['n']:,} | "
                f"{m['alpha']*100:+.2f}% |"
            )
        lines.append("")

    lines += [
        "---",
        f"*Generated by crypto-predictor v0.1.0 · formula_v1.5 · "
        f"asof {asof.isoformat()}*",
        "*Not financial advice. Backtest assumes no slippage.*",
    ]
    return "\n".join(lines)
```

- [ ] Step 4: Verify PASS

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/output/ tests/test_output/
git commit -m "feat(output): daily markdown report renderer (§15.1)"
git push
```

---

## Task 8.2: Telegram compact summary

**Files:**
- Create: `src/crypto_predictor/output/telegram_summary.py`
- Create: `tests/test_output/test_telegram_summary.py`

- [ ] Step 1: Failing test

```python
# tests/test_output/test_telegram_summary.py
from datetime import datetime, timezone

from crypto_predictor.orchestrator.ranker import RankedSlate
from crypto_predictor.output.telegram_summary import (
    render_telegram_summary, render_high_conviction_alert,
)


def test_render_telegram_summary_under_800_chars():
    slate = RankedSlate(
        top_long=[
            {"symbol": "SOL/USDT:USDT", "p_direction": 0.78, "target_value": 0.05},
            {"symbol": "AVAX/USDT:USDT", "p_direction": 0.74, "target_value": 0.048},
            {"symbol": "LINK/USDT:USDT", "p_direction": 0.73, "target_value": 0.041},
        ],
        top_short=[
            {"symbol": "ENS/USDT:USDT", "p_direction": 0.71, "target_value": -0.041},
            {"symbol": "NEAR/USDT:USDT", "p_direction": 0.69, "target_value": -0.038},
        ],
        wild_cards=[],
    )
    msg = render_telegram_summary(
        asof=datetime(2026, 6, 2, 6, 0, tzinfo=timezone.utc),
        regime="BULL",
        slate=slate,
        report_filename="reports/predict-2026-06-02-0600.md",
    )
    assert "Predictor" in msg
    assert "BULL" in msg
    assert "SOL" in msg
    assert len(msg) < 800


def test_render_high_conviction_alert_lists_candidates():
    candidates = [
        {"symbol": "SOL/USDT:USDT", "p_direction": 0.82, "target_value": 0.06,
         "rationale": "Funding ext negative."},
        {"symbol": "AVAX/USDT:USDT", "p_direction": 0.80, "target_value": 0.055,
         "rationale": "Momentum aligned."},
    ]
    msg = render_high_conviction_alert(candidates)
    assert "SOL" in msg
    assert "AVAX" in msg
    assert "High Conv" in msg or "high conv" in msg.lower()
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/output/telegram_summary.py
"""Telegram compact summary + high-conviction alerts."""
from __future__ import annotations

from datetime import datetime

from crypto_predictor.orchestrator.ranker import RankedSlate


def render_telegram_summary(*, asof: datetime, regime: str, slate: RankedSlate,
                            report_filename: str = "") -> str:
    """One-message daily summary, ≤ 800 chars."""
    lines = [
        f"🔮 Predictor {asof.strftime('%Y-%m-%d %H:%M UTC')} | {regime}",
        "",
    ]
    if slate.top_long:
        lines.append("📈 Top Long:")
        for i, p in enumerate(slate.top_long[:5], start=1):
            sym_short = p["symbol"].split("/")[0]
            lines.append(
                f"{i}. {sym_short:<6} P↑{p['p_direction']:.2f} "
                f"→ {p['target_value']:+.1%}"
            )
        lines.append("")
    if slate.top_short:
        lines.append("📉 Top Short:")
        for i, p in enumerate(slate.top_short[:5], start=1):
            sym_short = p["symbol"].split("/")[0]
            lines.append(
                f"{i}. {sym_short:<6} P↓{p['p_direction']:.2f} "
                f"→ {p['target_value']:+.1%}"
            )
        lines.append("")
    if report_filename:
        lines.append(f"📄 {report_filename}")
    return "\n".join(lines)


def render_high_conviction_alert(candidates: list[dict]) -> str:
    """One-message alert listing high-conviction picks (P>0.78 ∧ |ret|>4%)."""
    if not candidates:
        return ""
    lines = ["⚡ High Conviction Alerts:", ""]
    for p in candidates:
        sym_short = p["symbol"].split("/")[0]
        rationale = p.get("rationale", "")[:80]
        direction = "↑" if p.get("prediction", "up") == "up" else "↓"
        lines.append(
            f"• {sym_short} {direction} P={p['p_direction']:.2f} "
            f"ret={p['target_value']:+.1%}\n  {rationale}"
        )
    return "\n".join(lines)
```

- [ ] Step 4: Verify PASS (2 tests)

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/output/telegram_summary.py tests/test_output/test_telegram_summary.py
git commit -m "feat(output): Telegram summary + high-conviction alert formatters"
git push
```

---

## Task 8.3: Thresholds config + alert routing

**Files:**
- Create: `data/thresholds.yaml`
- Create: `src/crypto_predictor/output/thresholds.py`
- Create: `tests/test_output/test_thresholds.py`

- [ ] Step 1: Failing test

```python
# tests/test_output/test_thresholds.py
from pathlib import Path

from crypto_predictor.output.thresholds import (
    load_thresholds, classify_high_conviction,
)


def test_load_thresholds_returns_defaults_when_missing(tmp_path: Path):
    t = load_thresholds(tmp_path / "missing.yaml")
    assert "high_conv_p" in t
    assert "high_conv_ret" in t
    assert t["high_conv_p"] > 0.5
    assert t["high_conv_ret"] > 0.0


def test_classify_high_conviction_filters():
    thresholds = {"high_conv_p": 0.78, "high_conv_ret": 0.04}
    rows = [
        {"symbol": "SOL", "p_direction": 0.82, "target_value": 0.06,
         "confidence_flag": "HIGH_CONV"},
        {"symbol": "ETH", "p_direction": 0.55, "target_value": 0.03,
         "confidence_flag": "NORMAL"},  # below both thresholds
        {"symbol": "AGIX", "p_direction": 0.81, "target_value": 0.07,
         "confidence_flag": "WILD_CARD"},  # wild card excluded
    ]
    high = classify_high_conviction(rows, thresholds)
    assert "SOL" in [r["symbol"] for r in high]
    assert "ETH" not in [r["symbol"] for r in high]
    assert "AGIX" not in [r["symbol"] for r in high]  # wild cards never high-conv
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```yaml
# data/thresholds.yaml
high_conv_p: 0.78
high_conv_ret: 0.04
calibration_drift_brier_delta: 0.05
pattern_seek_min: 0.65
pattern_avoid_max: 0.50
```

```python
# src/crypto_predictor/output/thresholds.py
"""Alert routing thresholds — load from YAML, classify predictions."""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULTS = {
    "high_conv_p": 0.78,
    "high_conv_ret": 0.04,
    "calibration_drift_brier_delta": 0.05,
    "pattern_seek_min": 0.65,
    "pattern_avoid_max": 0.50,
}


def load_thresholds(path: Path) -> dict:
    if not path.exists():
        return dict(DEFAULTS)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    merged = dict(DEFAULTS)
    merged.update(raw)
    return merged


def classify_high_conviction(predictions: list[dict],
                              thresholds: dict) -> list[dict]:
    """Return predictions that meet high-conviction criteria (excludes wild cards)."""
    p_thresh = thresholds["high_conv_p"]
    ret_thresh = thresholds["high_conv_ret"]
    return [
        p for p in predictions
        if p.get("confidence_flag") != "WILD_CARD"
        and p["p_direction"] >= p_thresh
        and abs(p["target_value"]) >= ret_thresh
    ]
```

- [ ] Step 4: Verify PASS (2 tests)

- [ ] Step 5: Commit + push

```powershell
git add data/thresholds.yaml src/crypto_predictor/output/thresholds.py tests/test_output/test_thresholds.py
git commit -m "feat(output): thresholds config + high-conviction classifier"
git push
```

---

## Task 8.4: Telegram delivery glue (reuse intel-hub MCP)

**Files:**
- Create: `src/crypto_predictor/output/telegram_delivery.py`
- Create: `tests/test_output/test_telegram_delivery.py`

**Purpose:** Send messages to Telegram. The user's `crypto-intel-hub` plugin has a `crypto-telegram` MCP — we shell out to it via a subprocess, OR we use the same `httpx` + bot token directly. Direct httpx is simpler and avoids cross-plugin coupling.

- [ ] Step 1: Failing test

```python
# tests/test_output/test_telegram_delivery.py
from unittest.mock import MagicMock, patch

from crypto_predictor.output.telegram_delivery import send_message


def test_send_message_calls_telegram_api(monkeypatch):
    fake_resp = MagicMock(status_code=200, text="ok")
    fake_post = MagicMock(return_value=fake_resp)
    monkeypatch.setattr("httpx.post", fake_post)
    ok = send_message(bot_token="FAKE", chat_id="123",
                      text="hello", disable_preview=True)
    assert ok is True
    args, kwargs = fake_post.call_args
    assert "sendMessage" in args[0]
    assert kwargs["json"]["chat_id"] == "123"
    assert kwargs["json"]["text"] == "hello"


def test_send_message_returns_false_on_error(monkeypatch):
    fake_resp = MagicMock(status_code=500, text="server error")
    fake_post = MagicMock(return_value=fake_resp)
    monkeypatch.setattr("httpx.post", fake_post)
    ok = send_message(bot_token="FAKE", chat_id="123", text="x")
    assert ok is False


def test_send_message_skips_when_no_token():
    ok = send_message(bot_token="", chat_id="123", text="x")
    assert ok is False
```

- [ ] Step 2: Verify FAIL

- [ ] Step 3: Implement

```python
# src/crypto_predictor/output/telegram_delivery.py
"""Telegram delivery via Bot API (httpx)."""
from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(*, bot_token: str, chat_id: str, text: str,
                 disable_preview: bool = True) -> bool:
    """Send a Telegram message via the Bot API. Returns True on success."""
    if not bot_token or not chat_id:
        log.warning("telegram_skipped_no_token")
        return False
    url = TELEGRAM_API.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_preview,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=20.0)
        if resp.status_code == 200:
            return True
        log.warning("telegram_send_failed",
                    status=resp.status_code, body=resp.text[:200])
        return False
    except Exception as exc:
        log.warning("telegram_send_exception", error=str(exc))
        return False
```

- [ ] Step 4: Verify PASS (3 tests)

- [ ] Step 5: Commit + push

```powershell
git add src/crypto_predictor/output/telegram_delivery.py tests/test_output/test_telegram_delivery.py
git commit -m "feat(output): Telegram delivery via Bot API with redaction-safe defaults"
git push
```

---

## Task 8.5: Compose Plan C delivery in scheduler job

**Files:**
- Modify: `src/crypto_predictor/scheduler/jobs.py` (extend `_job_predict_scan`)

- [ ] Step 1: Extend `_job_predict_scan` to write the markdown report AND send Telegram

After the `run_full_scan` call in `_job_predict_scan`, append:

```python
from crypto_predictor.config import load_secrets
from crypto_predictor.output.markdown_report import render_daily_report
from crypto_predictor.output.telegram_summary import (
    render_telegram_summary, render_high_conviction_alert,
)
from crypto_predictor.output.telegram_delivery import send_message
from crypto_predictor.output.thresholds import (
    load_thresholds, classify_high_conviction,
)

# After result = run_full_scan(...):
slate = result["slate"]
asof = datetime.now(timezone.utc)

# Markdown report
report_md = render_daily_report(
    asof=asof, regime=result["scan"]["regime"], slate=slate,
    n_scanned=len(symbols), n_skipped=result["scan"]["n_skipped"],
    rolling_metrics={},  # populated in Plan D (B-loop metrics)
)
report_dir = project_root / "reports"
report_dir.mkdir(parents=True, exist_ok=True)
report_filename = report_dir / f"predict-{asof.strftime('%Y-%m-%d-%H%M')}.md"
report_filename.write_text(report_md, encoding="utf-8")
log.info("daily_report_written", path=str(report_filename))

# Telegram
secrets = load_secrets(project_root / "data" / "secrets.env")
bot_token = secrets.get("TELEGRAM_BOT_TOKEN", "")
chat_id = secrets.get("TELEGRAM_CHAT_ID", "")
if bot_token and chat_id:
    summary = render_telegram_summary(
        asof=asof, regime=result["scan"]["regime"], slate=slate,
        report_filename=f"reports/{report_filename.name}",
    )
    send_message(bot_token=bot_token, chat_id=chat_id, text=summary)

    # High-conviction alert (separate message)
    thresholds = load_thresholds(project_root / "data" / "thresholds.yaml")
    high_conv = classify_high_conviction(
        slate.top_long + slate.top_short, thresholds,
    )
    if high_conv:
        alert = render_high_conviction_alert(high_conv[:10])
        send_message(bot_token=bot_token, chat_id=chat_id, text=alert)
```

- [ ] Step 2: Run existing test suite to confirm nothing breaks

```powershell
.\.venv\Scripts\python.exe -m pytest -v --tb=short
```

- [ ] Step 3: Manually trigger the job (dry-run, may send to Telegram if secrets are set)

```powershell
.\.venv\Scripts\python.exe scripts\predict_scan_cli.py
```

Verify: a markdown file appears under `reports/predict-YYYY-MM-DD-HHMM.md`, and a Telegram message arrives if secrets are set.

- [ ] Step 4: Commit + push

```powershell
git add src/crypto_predictor/scheduler/jobs.py
git commit -m "feat(scheduler): predict_scan job writes markdown + sends Telegram"
git push
```

---

## Task 8.6: Plan C integration test + completion report

**Files:**
- Create: `tests/integration/test_plan_c_integration.py`
- Create: `docs/plans/2026-XX-XX-plan-c-completion-report.md`

- [ ] Step 1: Integration test

```python
# tests/integration/test_plan_c_integration.py
"""Plan C end-to-end: scan + rank + narrate + render + (mock) deliver."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_predictor.orchestrator.run import run_full_scan
from crypto_predictor.output.markdown_report import render_daily_report
from crypto_predictor.output.telegram_summary import render_telegram_summary
from crypto_predictor.storage.predictions_db import init_db

REPO_ROOT = Path(__file__).resolve().parents[2]
HISTORY_ROOT = REPO_ROOT / "data" / "history"
SECTOR_MAP = REPO_ROOT / "data" / "sector_map.yaml"
CALIB = REPO_ROOT / "data" / "calibration_1_5_4.json"


@pytest.mark.skipif(
    not (HISTORY_ROOT / "ohlcv" / "BTC_USDT_USDT" / "1h.parquet").exists(),
    reason="ingest not done",
)
def test_plan_c_end_to_end(tmp_path: Path):
    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
               "BNB/USDT:USDT", "XRP/USDT:USDT"]
    db = tmp_path / "predictions.db"
    init_db(db)
    mcap_ranks = {s: i + 1 for i, s in enumerate(symbols)}
    asof = datetime.now(timezone.utc)
    result = run_full_scan(
        history_root=HISTORY_ROOT,
        sentiment_cache=tmp_path / "sentiment.db",
        global_cache=tmp_path / "global.db",
        sector_map=SECTOR_MAP,
        predictions_db=db,
        calibration_path=CALIB if CALIB.exists() else None,
        symbols=symbols, mcap_ranks=mcap_ranks,
        asof=asof, formula_version="v1.5",
        k_long=3, k_short=3, llm_client=None,
    )
    slate = result["slate"]
    assert result["scan"]["n_predictions"] > 0
    assert isinstance(render_daily_report(
        asof=asof, regime=result["scan"]["regime"], slate=slate,
        n_scanned=5, n_skipped=0, rolling_metrics={},
    ), str)
    tg = render_telegram_summary(
        asof=asof, regime=result["scan"]["regime"], slate=slate,
    )
    assert len(tg) < 800
```

- [ ] Step 2: Run + verify

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_plan_c_integration.py -v
```

Expected: PASSED.

- [ ] Step 3: Write completion report

Mirror the structure of `2026-06-02-plan-b-completion-report.md`. Sections: summary, what shipped, what didn't (Plan D), Plan C commits, recommendation for Plan D scope.

- [ ] Step 4: Commit + push

```powershell
git add tests/integration/test_plan_c_integration.py docs/plans/2026-XX-XX-plan-c-completion-report.md
git commit -m "test(integration): Plan C end-to-end + completion report"
git push
```

---

## Plan C complete — handoff to Plan D

✅ **What Plan C delivers:**

| Capability | Status |
|---|---|
| Daily orchestrator (`run_full_scan`) | ✓ |
| Predictions persisted to `predictions.db` | ✓ |
| Top-K long/short/wild-card ranking | ✓ |
| Claude Haiku rationale (graceful fallback) | ✓ |
| Markdown daily report (§15.1) | ✓ |
| Telegram compact summary (§15.2) | ✓ |
| Selective high-conviction alerts | ✓ |
| `/predict-scan` slash command | ✓ |
| Scheduler 06:00 UTC trigger wired | ✓ |
| Plan C integration test on real BTC/ETH/SOL/BNB/XRP | ✓ |

❌ **What Plan C does NOT yet do (Plan D):**
- Validate live predictions (24h forward check) — Plan D
- Rolling metrics (`metrics_rolling` table population) — Plan D
- Pattern detector — Plan D
- Calibration drift detection + auto-recalibration — Plan D
- Benchmark tracker (alpha vs equal-weight, daily attribution) — Plan D
- Sentiment + global cache fetchers (NewsAPI, LunarCrush, crypto-data MCP) — opportunistic, can ship in Plan D or as a separate Phase 1.5+ task

---

**Next step:** When Plan C is complete, say "Plan D yaz" — Week 9–10 covers the validation/feedback loop that turns daily predictions into a self-learning track record.

---

*End of Plan C.*
