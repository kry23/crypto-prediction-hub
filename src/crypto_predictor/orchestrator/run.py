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
from crypto_predictor.orchestrator.feature_completeness import (
    detect_feature_completeness,
)
from crypto_predictor.orchestrator.llm_summary import (
    generate_rationale, summarize_top_signals,
)
from crypto_predictor.orchestrator.ranker import rank_predictions, RankedSlate

log = structlog.get_logger(__name__)


def _log_missing_caches(sentiment_cache: Path, global_cache: Path) -> None:
    """Emit one warning per missing cache file (operator visibility)."""
    if not sentiment_cache.exists():
        log.warning("cache_missing", cache="sentiment", path=str(sentiment_cache))
    if not global_cache.exists():
        log.warning("cache_missing", cache="global", path=str(global_cache))


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


def _load_predictions(db: Path, asof: datetime,
                      tolerance_seconds: int = 60) -> list[dict]:
    """Load predictions inserted near `asof` (range query, not exact match).

    Previously did `WHERE created_at = asof.isoformat()`. If any caller ever
    re-derived `asof` between the write and the read (e.g., two separate
    `datetime.now()` calls in jobs.py), the lookup silently returned zero
    rows. The asof consolidation in `_job_predict_scan` removed the current
    drift but the brittle exact-match is a future-proofing hazard.

    A ±60s window covers the scan-write-then-load handoff (~ms) while still
    excluding any other cohort persisted on a different cron firing.
    """
    from datetime import timedelta
    lo = (asof - timedelta(seconds=tolerance_seconds)).isoformat()
    hi = (asof + timedelta(seconds=tolerance_seconds)).isoformat()
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT id, symbol, prediction, p_direction, target_value, "
            "       composite_score, confidence_flag, regime "
            "FROM predictions "
            "WHERE created_at >= ? AND created_at <= ?",
            (lo, hi),
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
                  llm_client=None,
                  mode: str = "live",
                  calibration_version: str = "1_5_4") -> dict:
    """End-to-end daily scan: predict + persist + rank + narrate.

    v0.2.1: ``mode`` (``"live"`` | ``"shadow"``) and ``calibration_version``
    are threaded through to the persistence layer so each prediction row
    records the runtime context. ``feature_completeness`` is derived from
    cache-file existence (first-cut approximation — passing ``None`` for the
    feature dicts means ``detect_feature_completeness`` falls back to
    file-existence-only checks, which matches the v0.2.1 spec for the
    operator-visibility loop).
    """
    _log_missing_caches(sentiment_cache, global_cache)
    # First-cut approximation: rely on file-existence checks via passing
    # None for the feature dicts. Per-symbol feature dicts are populated
    # downstream inside run_daily_scan; pre-computing them here would
    # duplicate work and require re-plumbing FeatureFetcher. For v0.2.1
    # this is sufficient because cache absence is the dominant degraded
    # signal we want to flag.
    completeness, missing_features = detect_feature_completeness(
        sentiment_cache=sentiment_cache, global_cache=global_cache,
        sentiment_features=None, global_features=None,
    )
    log.info("feature_completeness_detected",
             completeness=completeness, missing_features=missing_features,
             mode=mode, calibration_version=calibration_version)
    scan = run_daily_scan(
        history_root=history_root,
        sentiment_cache=sentiment_cache, global_cache=global_cache,
        sector_map=sector_map, predictions_db=predictions_db,
        calibration_path=calibration_path,
        symbols=symbols, mcap_ranks=mcap_ranks,
        asof=asof, formula_version=formula_version,
        global_mcap_trend=global_mcap_trend,
        mode=mode,
        feature_completeness=completeness,
        missing_features=missing_features,
        calibration_version=calibration_version,
    )

    rows = _load_predictions(predictions_db, asof)
    slate = rank_predictions(rows, k_long=k_long, k_short=k_short)

    fetcher = FeatureFetcher(root=history_root, asof=asof)
    _narrate_slate(slate, fetcher=fetcher,
                   sentiment_cache=sentiment_cache, global_cache=global_cache,
                   sector_map=sector_map, mcap_ranks=mcap_ranks,
                   llm_client=llm_client)

    return {"scan": scan, "slate": slate}
