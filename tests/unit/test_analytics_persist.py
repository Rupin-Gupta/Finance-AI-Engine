import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from backend.analytics.indicators import add_all_indicators
from backend.db.queries import analytics as analytics_queries


class FakeConn:
    def __init__(self):
        self.rows = []
        self.fetched = []

    async def executemany(self, query, rows):
        assert "INSERT INTO analytics" in query
        self.rows.extend(rows)

    async def fetch(self, query, *args):
        return self.fetched


def make_ohlcv_df(n=50):
    ts_base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prices = np.cumsum(np.random.randn(n)) + 100
    return pd.DataFrame({
        "symbol": ["AAPL"] * n,
        "timestamp": pd.date_range(ts_base, periods=n, freq="D"),
        "open": prices,
        "high": prices + 1,
        "low": prices - 1,
        "close": prices,
        "volume": np.random.randint(1000, 5000, n),
    })


@pytest.mark.asyncio
async def test_upsert_analytics_writes_rows():
    conn = FakeConn()
    df = make_ohlcv_df(50)
    df = add_all_indicators(df)
    records = df[
        ["symbol", "timestamp", "sma_20", "ema_20", "rsi_14", "volatility_20", "momentum_10"]
    ].to_dict("records")

    count = await analytics_queries.upsert_analytics(conn, records)

    assert count == 50
    assert len(conn.rows) == 50
    # each row: (symbol, timestamp, sma_20, ema_20, rsi_14, volatility_20, momentum_10)
    sym, ts, sma, ema, rsi, vol, mom = conn.rows[-1]
    assert sym == "AAPL"
    assert isinstance(ts, (datetime, pd.Timestamp))


@pytest.mark.asyncio
async def test_upsert_analytics_coerces_nan_to_none():
    conn = FakeConn()
    # First 19 rows have NaN sma_20 (window=20)
    df = make_ohlcv_df(50)
    df = add_all_indicators(df)
    records = df[
        ["symbol", "timestamp", "sma_20", "ema_20", "rsi_14", "volatility_20", "momentum_10"]
    ].to_dict("records")

    await analytics_queries.upsert_analytics(conn, records)

    # rows 0-18: sma_20 should be None (NaN coerced)
    for i in range(19):
        assert conn.rows[i][2] is None, f"row {i} sma_20 should be None"

    # row 19+: sma_20 should be float
    assert isinstance(conn.rows[19][2], float)


@pytest.mark.asyncio
async def test_get_analytics_returns_fetched_rows():
    ts = datetime(2026, 1, 2, tzinfo=timezone.utc)
    fake_record = {"symbol": "AAPL", "timestamp": ts, "sma_20": 101.5,
                   "ema_20": 101.2, "rsi_14": 55.0, "volatility_20": 0.2, "momentum_10": 0.01}
    conn = FakeConn()
    conn.fetched = [fake_record]

    result = await analytics_queries.get_analytics(conn, "AAPL", ts, ts)

    assert result == [fake_record]
