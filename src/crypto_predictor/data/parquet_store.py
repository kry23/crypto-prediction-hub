"""Parquet-backed historical store, partitioned by data_kind/symbol/timeframe."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def safe_symbol(symbol: str) -> str:
    """Sanitize a ccxt unified symbol for filesystem path use.

    'BTC/USDT:USDT' -> 'BTC_USDT_USDT'
    'BTC-USDT-SWAP' -> 'BTC-USDT-SWAP' (already safe)
    """
    return symbol.replace("/", "_").replace(":", "_")


def parquet_path(root: Path, symbol: str, timeframe: str,
                 data_kind: str = "ohlcv") -> Path:
    """Return the canonical parquet path for (data_kind, symbol, timeframe)."""
    return root / data_kind / safe_symbol(symbol) / f"{timeframe}.parquet"


def write_ohlcv(root: Path, symbol: str, timeframe: str,
                df: pd.DataFrame) -> None:
    """Overwrite the OHLCV parquet for (symbol, timeframe)."""
    path = parquet_path(root, symbol, timeframe, "ohlcv")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def append_ohlcv(root: Path, symbol: str, timeframe: str,
                 df: pd.DataFrame) -> None:
    """Append OHLCV rows, deduplicating on timestamp."""
    existing = read_ohlcv(root, symbol, timeframe)
    if existing.empty:
        write_ohlcv(root, symbol, timeframe, df)
        return
    combined = (
        pd.concat([existing, df], ignore_index=True)
        .drop_duplicates(subset=["timestamp"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    write_ohlcv(root, symbol, timeframe, combined)


def read_ohlcv(root: Path, symbol: str, timeframe: str) -> pd.DataFrame:
    """Read OHLCV parquet; return empty frame with canonical columns if missing."""
    path = parquet_path(root, symbol, timeframe, "ohlcv")
    if not path.exists():
        return pd.DataFrame(columns=[
            "timestamp", "open", "high", "low", "close", "volume"
        ])
    return pd.read_parquet(path)
