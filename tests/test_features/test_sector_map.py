from pathlib import Path

import yaml

from crypto_predictor.features.sector_map import classify_sector


def test_classify_btc_returns_btc(tmp_path: Path):
    yfile = tmp_path / "sector_map.yaml"
    yfile.write_text(yaml.safe_dump({
        "btc": ["BTC-USDT-SWAP"],
        "eth": ["ETH-USDT-SWAP"],
        "defi": ["AAVE-USDT-SWAP", "UNI-USDT-SWAP"],
        "l1": ["SOL-USDT-SWAP", "AVAX-USDT-SWAP"],
    }))
    assert classify_sector("BTC-USDT-SWAP", yfile) == "btc"
    assert classify_sector("AAVE-USDT-SWAP", yfile) == "defi"


def test_unknown_coin_returns_l1_default(tmp_path: Path):
    yfile = tmp_path / "sector_map.yaml"
    yfile.write_text(yaml.safe_dump({"btc": ["BTC-USDT-SWAP"]}))
    assert classify_sector("ZZZ-USDT-SWAP", yfile) == "l1"
