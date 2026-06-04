# tests/test_scripts/test_generate_mcap_ranks.py
"""Unit tests for the build_mcap_map helper. The CoinGecko fetch itself is
not unit-tested (network), only the parsing/dedupe logic."""
from scripts.generate_mcap_ranks import build_mcap_map


def test_build_mcap_map_uppercases_symbols():
    markets = [
        {"symbol": "btc", "market_cap_rank": 1},
        {"symbol": "eth", "market_cap_rank": 2},
    ]
    out = build_mcap_map(markets)
    assert out == {"BTC": 1, "ETH": 2}


def test_build_mcap_map_skips_missing_rank():
    markets = [
        {"symbol": "btc", "market_cap_rank": 1},
        {"symbol": "newcoin", "market_cap_rank": None},
    ]
    out = build_mcap_map(markets)
    assert out == {"BTC": 1}
    assert "NEWCOIN" not in out


def test_build_mcap_map_skips_missing_symbol():
    markets = [
        {"symbol": None, "market_cap_rank": 1},
        {"symbol": "eth", "market_cap_rank": 2},
    ]
    out = build_mcap_map(markets)
    assert out == {"ETH": 2}


def test_build_mcap_map_dedup_keeps_first_higher_rank():
    """When two coins share a base symbol, the list is mcap-desc so the
    first one (higher mcap = lower rank) should win."""
    markets = [
        {"symbol": "BTC", "market_cap_rank": 1},  # Bitcoin
        {"symbol": "btc", "market_cap_rank": 850},  # some clone
    ]
    out = build_mcap_map(markets)
    assert out == {"BTC": 1}


def test_build_mcap_map_empty_input():
    assert build_mcap_map([]) == {}
