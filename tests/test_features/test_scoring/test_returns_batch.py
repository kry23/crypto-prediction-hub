from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from crypto_predictor.data.parquet_store import write_ohlcv
from crypto_predictor.scoring.returns import actual_returns_batch


def _seed(root: Path, sym: str, n: int = 60):
    rows = []
    p = 100.0
    for i in range(n):
        p *= 1.001
        rows.append({"timestamp": 1700000000000 + i * 3600 * 1000,
                     "open": p, "high": p * 1.01, "low": p * 0.99,
                     "close": p, "volume": 1000})
    write_ohlcv(root, sym, "1h", pd.DataFrame(rows))


def test_batch_resolves_returns(tmp_path: Path):
    _seed(tmp_path, "BTC-USDT-SWAP", n=60)
    _seed(tmp_path, "ETH-USDT-SWAP", n=60)
    start = datetime.fromtimestamp(
        (1700000000000 + 20 * 3600 * 1000) / 1000, tz=timezone.utc
    )
    out = actual_returns_batch(
        root=tmp_path,
        items=[
            ("BTC-USDT-SWAP", start, 24),
            ("ETH-USDT-SWAP", start, 24),
            ("UNKNOWN", start, 24),
        ],
    )
    assert len(out) == 3
    assert out[0] is not None
    assert out[1] is not None
    assert out[2] is None
