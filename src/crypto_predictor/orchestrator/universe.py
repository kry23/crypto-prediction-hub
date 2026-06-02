"""Symbol universe + mcap-rank discovery."""
from __future__ import annotations

from crypto_predictor.data.okx_client import ccxt_to_base_ccy


def list_active_perps(ccxt_client) -> list[str]:
    """Return list of active USDT-settled perpetual symbols on OKX."""
    markets = ccxt_client.load_markets()
    return [
        m["symbol"] for m in markets.values()
        if m.get("swap") and m.get("settle") == "USDT" and m.get("active")
    ]


def assign_mcap_ranks(symbols: list[str],
                      mcap_map: dict[str, int]) -> dict[str, int | None]:
    """Map each symbol to a mcap rank, or None if unknown."""
    out: dict[str, int | None] = {}
    for sym in symbols:
        base = ccxt_to_base_ccy(sym)
        out[sym] = mcap_map.get(base)
    return out
