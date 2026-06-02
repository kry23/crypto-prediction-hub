from unittest.mock import MagicMock

from crypto_predictor.orchestrator.universe import (
    list_active_perps, assign_mcap_ranks,
)


def test_list_active_perps_filters_usdt_settled():
    fake = MagicMock()
    fake.load_markets.return_value = {
        "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "swap": True,
                          "settle": "USDT", "active": True},
        "ETH/USD:USD": {"symbol": "ETH/USD:USD", "swap": True,
                        "settle": "USD", "active": True},  # not USDT
        "BTC/USDT": {"symbol": "BTC/USDT", "swap": False,
                     "settle": "USDT", "active": True},  # spot
        "DEAD/USDT:USDT": {"symbol": "DEAD/USDT:USDT", "swap": True,
                           "settle": "USDT", "active": False},  # delisted
    }
    symbols = list_active_perps(fake)
    assert "BTC/USDT:USDT" in symbols
    assert "ETH/USD:USD" not in symbols
    assert "BTC/USDT" not in symbols
    assert "DEAD/USDT:USDT" not in symbols


def test_assign_mcap_ranks_from_dict():
    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "ZZZ/USDT:USDT"]
    mcap_map = {"BTC": 1, "ETH": 2}  # ZZZ unknown
    ranks = assign_mcap_ranks(symbols, mcap_map)
    assert ranks["BTC/USDT:USDT"] == 1
    assert ranks["ETH/USDT:USDT"] == 2
    assert ranks["ZZZ/USDT:USDT"] is None
