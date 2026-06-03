"""Symbol universe + mcap-rank discovery."""
from __future__ import annotations

from pathlib import Path

import structlog
import yaml

from crypto_predictor.data.okx_client import ccxt_to_base_ccy

log = structlog.get_logger(__name__)


def load_blacklist(path: Path) -> set[str]:
    """Read base-currency blacklist from YAML; empty set if missing/empty."""
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("blacklist") or []
    out: set[str] = set()
    for entry in raw:
        if isinstance(entry, str):
            out.add(entry)
        else:
            log.warning("blacklist_skip_non_string",
                        entry=repr(entry), type=type(entry).__name__)
    return out


def list_active_perps(ccxt_client, blacklist_path: Path | None = None) -> list[str]:
    """Return list of active USDT-settled perpetual symbols on OKX."""
    markets = ccxt_client.load_markets()
    symbols = [
        m["symbol"] for m in markets.values()
        if m.get("swap") and m.get("settle") == "USDT" and m.get("active")
    ]
    if blacklist_path is None:
        return symbols
    blacklist = load_blacklist(blacklist_path)
    if not blacklist:
        return symbols
    kept = [s for s in symbols if ccxt_to_base_ccy(s) not in blacklist]
    excluded = [s for s in symbols if ccxt_to_base_ccy(s) in blacklist]
    if excluded:
        log.info("blacklist_applied",
                 excluded_count=len(excluded), sample=excluded[:5])
    return kept


def assign_mcap_ranks(symbols: list[str],
                      mcap_map: dict[str, int]) -> dict[str, int | None]:
    """Map each symbol to a mcap rank, or None if unknown."""
    out: dict[str, int | None] = {}
    for sym in symbols:
        base = ccxt_to_base_ccy(sym)
        out[sym] = mcap_map.get(base)
    return out
