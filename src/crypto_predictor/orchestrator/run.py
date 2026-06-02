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
