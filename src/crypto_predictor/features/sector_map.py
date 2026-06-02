"""Sector classification: which family does a coin belong to."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


@lru_cache(maxsize=4)
def _load(path: Path) -> dict[str, list[str]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def classify_sector(symbol: str, sector_map_path: Path) -> str:
    """Return 'btc'|'eth'|'defi'|'l1' (default 'l1' if unknown)."""
    m = _load(sector_map_path)
    for sector, coins in m.items():
        if symbol in coins:
            return sector
    return "l1"
