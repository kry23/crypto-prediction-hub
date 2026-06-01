"""asof-guarded data fetcher used by every feature computation.

CRITICAL: every read MUST go through this class so look-ahead bias is
impossible in backtest. Tests in tests/test_features/test_fetcher_asof_guard.py
enforce this invariant.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import parquet_path


@dataclass(frozen=True)
class FeatureFetcher:
    """Fetcher pinned to a specific point in time. All reads filter timestamps < asof."""

    root: Path
    asof: datetime

    @property
    def _asof_ms(self) -> int:
        return int(self.asof.timestamp() * 1000)

    def ohlcv(self, symbol: str, timeframe: str,
              lookback_bars: int) -> pd.DataFrame:
        """Return the last `lookback_bars` OHLCV rows strictly before asof."""
        path = parquet_path(self.root, symbol, timeframe, "ohlcv")
        if not path.exists():
            return pd.DataFrame(columns=[
                "timestamp", "open", "high", "low", "close", "volume"
            ])
        df = pd.read_parquet(path)
        df = df[df["timestamp"] < self._asof_ms]
        return df.tail(lookback_bars).reset_index(drop=True)

    def funding(self, symbol: str, lookback_rows: int) -> pd.DataFrame:
        path = parquet_path(self.root, symbol, "funding", "futures")
        if not path.exists():
            return pd.DataFrame(columns=["timestamp", "funding_rate"])
        df = pd.read_parquet(path)
        df = df[df["timestamp"] < self._asof_ms]
        return df.tail(lookback_rows).reset_index(drop=True)

    def open_interest(self, symbol: str, lookback_rows: int) -> pd.DataFrame:
        path = parquet_path(self.root, symbol, "oi", "futures")
        if not path.exists():
            return pd.DataFrame(columns=["timestamp", "open_interest"])
        df = pd.read_parquet(path)
        df = df[df["timestamp"] < self._asof_ms]
        return df.tail(lookback_rows).reset_index(drop=True)

    def ls_ratio(self, symbol: str, lookback_rows: int) -> pd.DataFrame:
        path = parquet_path(self.root, symbol, "ls_ratio", "futures")
        if not path.exists():
            return pd.DataFrame(columns=["timestamp", "ls_ratio"])
        df = pd.read_parquet(path)
        df = df[df["timestamp"] < self._asof_ms]
        return df.tail(lookback_rows).reset_index(drop=True)

    def liquidations(self, symbol: str, lookback_rows: int) -> pd.DataFrame:
        path = parquet_path(self.root, symbol, "liq", "futures")
        if not path.exists():
            return pd.DataFrame(columns=["timestamp", "side", "size_usdt"])
        df = pd.read_parquet(path)
        df = df[df["timestamp"] < self._asof_ms]
        return df.tail(lookback_rows).reset_index(drop=True)
