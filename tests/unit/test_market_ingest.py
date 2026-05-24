from datetime import datetime, timezone

import pandas as pd
import pytest

from backend.ingest import market
from backend.ingest import pipeline as ingest_pipeline
from backend.ingest.pipeline import run_market_ingest


class FakeConn:
    def __init__(self):
        self.job_updates = []
        self.stock_rows = []
        self.market_rows = []

    async def fetchrow(self, query, *args):
        assert "INSERT INTO jobs" in query
        assert args == ("market_ingest",)
        return {"id": "job-1"}

    async def execute(self, query, *args):
        assert "UPDATE jobs" in query
        self.job_updates.append(args)

    async def executemany(self, query, rows):
        if "INSERT INTO stocks" in query:
            self.stock_rows.extend(rows)
        elif "INSERT INTO market_data" in query:
            self.market_rows.extend(rows)
        else:
            raise AssertionError(f"unexpected query: {query}")


@pytest.mark.asyncio
async def test_run_market_ingest_seeds_stocks_dedupes_and_tracks_job(monkeypatch):
    ts = datetime(2026, 1, 2, tzinfo=timezone.utc)

    async def fake_fetch_ohlcv(symbol, period, interval):
        assert symbol == "AAPL"
        assert period == "5d"
        assert interval == "1d"
        return [
            {
                "symbol": "AAPL",
                "timestamp": ts,
                "open": 100,
                "high": 110,
                "low": 95,
                "close": 105,
                "volume": 1000,
            },
            {
                "symbol": "AAPL",
                "timestamp": ts,
                "open": 101,
                "high": 111,
                "low": 96,
                "close": 106,
                "volume": 2000,
            },
        ]

    monkeypatch.setattr(ingest_pipeline, "fetch_ohlcv", fake_fetch_ohlcv)
    conn = FakeConn()

    job_id = await run_market_ingest(conn, [" aapl ", "AAPL"])

    assert job_id == "job-1"
    assert conn.stock_rows == [("AAPL",)]
    assert len(conn.market_rows) == 1
    assert conn.market_rows[0] == ("AAPL", ts, 101, 111, 96, 106, 2000)
    assert conn.job_updates == [("completed", None, "job-1")]


@pytest.mark.asyncio
async def test_run_market_ingest_marks_job_failed_on_invalid_rows(monkeypatch):
    async def fake_fetch_ohlcv(symbol, period, interval):
        return [
            {
                "symbol": symbol,
                "timestamp": datetime(2026, 1, 2, tzinfo=timezone.utc),
                "open": 100,
                "high": 110,
                "low": 95,
                "close": None,
                "volume": 1000,
            }
        ]

    monkeypatch.setattr(ingest_pipeline, "fetch_ohlcv", fake_fetch_ohlcv)
    conn = FakeConn()

    with pytest.raises(ValueError, match="null required fields"):
        await run_market_ingest(conn, ["MSFT"])

    assert conn.stock_rows == [("MSFT",)]
    assert conn.market_rows == []
    assert conn.job_updates == [("failed", "OHLCV row contains null required fields", "job-1")]


@pytest.mark.asyncio
async def test_fetch_ohlcv_normalizes_yfinance_rows(monkeypatch):
    def fake_download(symbol, period, interval):
        assert symbol == "AAPL"
        df = pd.DataFrame(
            {
                "Open": [100.0, None],
                "High": [110.0, 111.0],
                "Low": [95.0, 96.0],
                "Close": [105.0, 106.0],
                "Volume": [1000, 2000],
            },
            index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
        )
        df.index.name = "Date"
        return df

    monkeypatch.setattr(market, "_download_ohlcv", fake_download)

    rows = await market.fetch_ohlcv("aapl", period="5d", interval="1d")

    assert rows == [
        {
            "symbol": "AAPL",
            "timestamp": datetime(2026, 1, 2, tzinfo=timezone.utc),
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
            "volume": 1000,
        }
    ]
