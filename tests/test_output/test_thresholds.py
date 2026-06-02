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
         "confidence_flag": "NORMAL"},
        {"symbol": "AGIX", "p_direction": 0.81, "target_value": 0.07,
         "confidence_flag": "WILD_CARD"},
    ]
    high = classify_high_conviction(rows, thresholds)
    assert "SOL" in [r["symbol"] for r in high]
    assert "ETH" not in [r["symbol"] for r in high]
    assert "AGIX" not in [r["symbol"] for r in high]
