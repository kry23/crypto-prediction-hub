from pathlib import Path
from unittest.mock import MagicMock

from crypto_predictor.orchestrator.universe import (
    list_active_perps, assign_mcap_ranks, load_blacklist,
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


def _make_fake_okx(bases: list[str]) -> MagicMock:
    fake = MagicMock()
    fake.load_markets.return_value = {
        f"{b}/USDT:USDT": {"symbol": f"{b}/USDT:USDT", "swap": True,
                           "settle": "USDT", "active": True}
        for b in bases
    }
    return fake


def test_load_blacklist_missing_file_returns_empty(tmp_path: Path):
    assert load_blacklist(tmp_path / "nope.yaml") == set()


def test_load_blacklist_valid_file_returns_set(tmp_path: Path):
    p = tmp_path / "bl.yaml"
    p.write_text("blacklist:\n  - SPCX\n  - RKLB\n", encoding="utf-8")
    assert load_blacklist(p) == {"SPCX", "RKLB"}


def test_load_blacklist_empty_list_returns_empty(tmp_path: Path):
    p = tmp_path / "bl.yaml"
    p.write_text("blacklist: []\n", encoding="utf-8")
    assert load_blacklist(p) == set()


def test_load_blacklist_missing_key_returns_empty(tmp_path: Path):
    p = tmp_path / "bl.yaml"
    p.write_text("other_key: foo\n", encoding="utf-8")
    assert load_blacklist(p) == set()


def test_load_blacklist_mixed_types_skips_non_strings(tmp_path: Path, caplog):
    p = tmp_path / "bl.yaml"
    p.write_text("blacklist:\n  - SPCX\n  - 42\n  - RKLB\n", encoding="utf-8")
    result = load_blacklist(p)
    assert result == {"SPCX", "RKLB"}


def test_list_active_perps_no_blacklist_unchanged():
    fake = _make_fake_okx(["BTC", "ETH", "SPCX"])
    symbols = list_active_perps(fake)
    assert set(symbols) == {"BTC/USDT:USDT", "ETH/USDT:USDT", "SPCX/USDT:USDT"}


def test_list_active_perps_with_blacklist_excludes_matched(tmp_path: Path):
    fake = _make_fake_okx(["BTC", "ETH", "SPCX", "RKLB"])
    p = tmp_path / "bl.yaml"
    p.write_text("blacklist:\n  - SPCX\n  - RKLB\n", encoding="utf-8")
    symbols = list_active_perps(fake, blacklist_path=p)
    assert set(symbols) == {"BTC/USDT:USDT", "ETH/USDT:USDT"}


def test_list_active_perps_blacklist_path_missing_keeps_all(tmp_path: Path):
    fake = _make_fake_okx(["BTC", "SPCX"])
    symbols = list_active_perps(fake, blacklist_path=tmp_path / "nope.yaml")
    assert set(symbols) == {"BTC/USDT:USDT", "SPCX/USDT:USDT"}
