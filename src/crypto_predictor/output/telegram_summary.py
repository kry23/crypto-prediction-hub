"""Telegram compact summary + high-conviction alerts."""
from __future__ import annotations

from datetime import datetime

from crypto_predictor.orchestrator.ranker import RankedSlate


def render_telegram_summary(*, asof: datetime, regime: str, slate: RankedSlate,
                            report_filename: str = "") -> str:
    """One-message daily summary, <= 800 chars."""
    lines = [
        f"\U0001f52e Predictor {asof.strftime('%Y-%m-%d %H:%M UTC')} | {regime}",
        "",
    ]
    if slate.top_long:
        lines.append("\U0001f4c8 Top Long:")
        for i, p in enumerate(slate.top_long[:5], start=1):
            sym_short = p["symbol"].split("/")[0]
            lines.append(
                f"{i}. {sym_short:<6} P↑{p['p_direction']:.2f} "
                f"→ {p['target_value']:+.1%}"
            )
        lines.append("")
    if slate.top_short:
        lines.append("\U0001f4c9 Top Short:")
        for i, p in enumerate(slate.top_short[:5], start=1):
            sym_short = p["symbol"].split("/")[0]
            lines.append(
                f"{i}. {sym_short:<6} P↓{p['p_direction']:.2f} "
                f"→ {p['target_value']:+.1%}"
            )
        lines.append("")
    if report_filename:
        lines.append(f"\U0001f4c4 {report_filename}")
    return "\n".join(lines)


def render_high_conviction_alert(candidates: list[dict]) -> str:
    """One-message alert listing high-conviction picks."""
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
