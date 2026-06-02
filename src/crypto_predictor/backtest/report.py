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
        lines.append("> survivorship_bias: present - backtest excludes coins delisted during the window.")
    lines.append("")

    lines += [
        "## Overall",
        "",
        f"- **Hit rate**: {overall['hit_rate'] * 100:.1f}%",
        f"- **MAE**: {overall['mae'] * 100:.2f}%",
        f"- **Brier score**: {overall['brier']:.3f}",
        f"- **Predictions**: {overall['n_predictions']:,}",
        "",
    ]

    lines += ["## Per regime", "", "| Regime | Hit rate | n |", "|---|---|---|"]
    for regime, m in per_regime.items():
        lines.append(f"| {regime} | {m['hit_rate'] * 100:.1f}% | {m['n']:,} |")
    lines.append("")

    lines += [
        "## Calibration buckets",
        "",
        "| P bucket | predicted | empirical | n |",
        "|---|---|---|---|",
    ]
    for b in calibration_buckets:
        lines.append(
            f"| {b['bucket_low']:.1f}-{b['bucket_high']:.1f} | "
            f"{b['predicted_mean']:.3f} | {b['empirical_rate']:.3f} | {b['n']:,} |"
        )
    lines.append("")

    lines += [
        "## Top-K alpha (vs equal-weight universe)",
        "",
        f"- **Long alpha**: {top_k_alpha['long'] * 100:+.2f}%",
        f"- **Short alpha**: {top_k_alpha['short'] * 100:+.2f}%",
        f"- **Combined**: {top_k_alpha['combined'] * 100:+.2f}%",
        "",
    ]

    return "\n".join(lines)
