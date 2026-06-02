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
