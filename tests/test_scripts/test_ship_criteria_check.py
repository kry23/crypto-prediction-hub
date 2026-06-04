import pandas as pd
import pytest

from scripts.ship_criteria_check import (
    check_headline_bar,
    check_bucket_bar,
    format_telegram_message,
)


def _df(hit_rate: float = 0.65, n: int = 500) -> pd.DataFrame:
    import numpy as np
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "p_direction": rng.uniform(0.5, 0.9, n),
        "status": ["correct" if rng.uniform() < hit_rate else "incorrect"
                   for _ in range(n)],
    })


def test_headline_bar_passes_when_hit_rate_high_and_brier_low():
    # Construct a df where 64% are correct
    n = 1000
    correct = int(0.65 * n)
    df = pd.DataFrame({
        "p_direction": [0.65] * n,
        "status": ["correct"] * correct + ["incorrect"] * (n - correct),
    })
    result = check_headline_bar(df)
    assert result["hit_rate"] >= 0.625
    assert result["passes_hit_rate"] is True


def test_headline_bar_fails_below_baseline():
    n = 1000
    correct = int(0.50 * n)
    df = pd.DataFrame({
        "p_direction": [0.65] * n,
        "status": ["correct"] * correct + ["incorrect"] * (n - correct),
    })
    result = check_headline_bar(df)
    assert result["passes_hit_rate"] is False


def test_bucket_bar_skips_sparse_buckets():
    df = pd.DataFrame({
        "p_direction": [0.82] * 5 + [0.62] * 100,
        "status": ["correct"] * 60 + ["incorrect"] * 45,
    })
    result = check_bucket_bar(df, min_samples_per_bucket=20)
    # The [0.80, 0.95) bucket has only 5 samples -> not checked
    sparse_bucket = next(
        (b for b in result["buckets"]
         if b["lo"] == 0.80 and b["hi"] == 0.95),
        None,
    )
    assert sparse_bucket is None or sparse_bucket["soft_pass"] is True


def test_bucket_bar_flags_out_of_band_buckets():
    # Build a bucket where realized is 30pp below expected
    n = 50
    df = pd.DataFrame({
        "p_direction": [0.85] * n,
        "status": ["correct"] * 25 + ["incorrect"] * 25,  # 50% realized
    })
    result = check_bucket_bar(df, min_samples_per_bucket=20)
    bad = [b for b in result["buckets"]
           if b["lo"] == 0.80 and b["delta_pp"] > 10]
    assert len(bad) >= 1


def test_format_telegram_pass_case():
    result_ok = {
        "headline": {"hit_rate": 0.642, "brier": 0.214,
                     "passes_hit_rate": True, "passes_brier": True},
        "buckets": [
            {"lo": 0.50, "hi": 0.55, "n": 30, "realized": 0.55,
             "expected": 0.53, "delta_pp": 2.0, "soft_pass": False},
        ],
        "can_ship": True,
    }
    msg = format_telegram_message(result_ok)
    assert "READY FOR PROMOTION" in msg
    assert "64.2%" in msg


def test_format_telegram_fail_case():
    result_fail = {
        "headline": {"hit_rate": 0.42, "brier": 0.30,
                     "passes_hit_rate": False, "passes_brier": False},
        "buckets": [],
        "can_ship": False,
        "escalation_recommendation": "prior_alpha=5",
    }
    msg = format_telegram_message(result_fail)
    assert "NOT READY" in msg
    assert "prior_alpha=5" in msg


def test_zero_samples_edge_case():
    df = pd.DataFrame({"p_direction": [], "status": []})
    result = check_headline_bar(df)
    assert result["hit_rate"] == 0.0
    assert result["passes_hit_rate"] is False
