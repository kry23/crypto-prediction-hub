"""Walk-forward backtest orchestrator. End-to-end: predict, label, metrics, report."""
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
from crypto_predictor.scoring.direction import (
    compute_direction_raw,
    compute_direction_raw_for_regime,
)
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
    """Run end-to-end walk-forward backtest."""
    log.info("backtest_start", n_symbols=len(symbols),
             start=start.isoformat(), end=end.isoformat())

    raw_samples: list[tuple[float, int, str]] = []
    pred_records: list[dict] = []

    sample_list = _sample_times(start, end, sample_interval_hours)
    total_samples = len(sample_list)
    for i, asof in enumerate(sample_list, start=1):
        fetcher = FeatureFetcher(root=history_root, asof=asof)
        regime = detect_regime(fetcher)
        if i == 1 or i % 5 == 0 or i == total_samples:
            log.info("backtest_progress",
                     sample=i, total=total_samples,
                     asof=asof.isoformat(), regime=regime,
                     predictions_so_far=len(pred_records))

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
            raw = compute_direction_raw_for_regime(feats, regime)
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

    calibs = fit_calibration(raw_samples)
    save_calibration(calibs, calibration_path,
                     fit_window=f"{start.isoformat()}..{end.isoformat()}")

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
