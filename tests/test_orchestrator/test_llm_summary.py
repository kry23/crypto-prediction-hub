from unittest.mock import MagicMock, patch

from crypto_predictor.orchestrator.llm_summary import (
    generate_rationale, summarize_top_signals,
)


def test_summarize_top_signals_picks_three_highest_abs():
    feats = {
        "ret_24h_z": 0.5, "funding_z": -2.3, "rsi_14_1h": 60,
        "oi_growth_z": 1.5, "vol_z_24h": 0.1,
    }
    top = summarize_top_signals(feats, n=3)
    names = [t[0] for t in top]
    assert "funding_z" in names
    assert "oi_growth_z" in names
    # ret_24h_z = 0.5 vs rsi_14_1h = 60 — rsi_14_1h has higher absolute value
    # But the spec says: excluded={mcap_rank_weight, coin_btc_corr_30d}; rsi_14_1h NOT excluded
    # So top-3 by abs: rsi_14_1h (60), funding_z (-2.3), oi_growth_z (1.5)
    assert "rsi_14_1h" in names


def test_generate_rationale_returns_string_with_mock_llm(monkeypatch):
    fake_client = MagicMock()
    fake_message = MagicMock()
    fake_message.content = [MagicMock(text="Funding extreme negative; OI rising; momentum supportive.")]
    fake_client.messages.create.return_value = fake_message
    summary = generate_rationale(
        client=fake_client,
        symbol="BTC/USDT:USDT",
        prediction="up",
        p_direction=0.78,
        expected_return=0.05,
        top_signals=[("funding_z", -2.3), ("oi_growth_z", 1.5), ("ret_24h_z", 0.5)],
    )
    assert isinstance(summary, str)
    assert len(summary) > 10


def test_generate_rationale_returns_fallback_when_client_none():
    summary = generate_rationale(
        client=None,
        symbol="BTC/USDT:USDT",
        prediction="up",
        p_direction=0.78,
        expected_return=0.05,
        top_signals=[("funding_z", -2.3), ("oi_growth_z", 1.5), ("ret_24h_z", 0.5)],
    )
    assert "funding_z" in summary
