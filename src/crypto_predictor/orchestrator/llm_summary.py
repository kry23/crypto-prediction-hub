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
    direction = "up" if prediction == "up" else "down"
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
