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


def persist_predictions(*, predictions_db: Path,
                        predictions: list[dict]) -> None:
    """Persist a batch of prediction dicts into predictions.db.

    Each dict must contain the base prediction columns (id, symbol,
    horizon_hours, prediction, p_direction, target_value, composite_score,
    confidence_flag, regime, formula_version, calibration_version, status,
    created_at). The v0.2.1 mode/feature_completeness/missing_features keys
    are optional; missing keys default to 'live', 'full', None respectively
    so existing callers that don't yet thread shadow metadata keep working.
    """
    conn = sqlite3.connect(str(predictions_db))
    try:
        for pred in predictions:
            conn.execute(
                "INSERT INTO predictions ("
                "id, symbol, horizon_hours, prediction, p_direction, "
                "target_value, composite_score, confidence_flag, regime, "
                "formula_version, calibration_version, status, created_at, "
                "mode, feature_completeness, missing_features"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pred["id"], pred["symbol"], pred["horizon_hours"],
                    pred["prediction"], pred["p_direction"],
                    pred["target_value"], pred["composite_score"],
                    pred["confidence_flag"], pred["regime"],
                    pred["formula_version"], pred["calibration_version"],
                    pred["status"], pred["created_at"],
                    pred.get("mode", "live"),
                    pred.get("feature_completeness", "full"),
                    pred.get("missing_features"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


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
            # Direction sign comes from CALIBRATED probability, not raw.
            # This guarantees sign(expected_ret) == sign(p_up - 0.5),
            # so prediction == "up" iff target_value > 0.
            calibrated_direction_for_magnitude = max(-1.0, min(1.0, (p_up - 0.5) * 2.0))
            expected_ret = compute_expected_return(
                fetcher, sym, direction_raw=calibrated_direction_for_magnitude, regime=regime
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
            # v0.2 — persist per-prediction feature snapshots for pattern mining
            for fname, fvalue in feats.items():
                if fvalue is None:
                    continue
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO predictions_features("
                        "prediction_id, feature_name, raw_value, z_value"
                        ") VALUES (?, ?, ?, NULL)",
                        (pred_id, fname, float(fvalue)),
                    )
                except (TypeError, ValueError):
                    # Skip non-numeric features (string keys etc)
                    continue
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
