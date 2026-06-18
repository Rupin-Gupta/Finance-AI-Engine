import asyncio
from datetime import timezone

import httpx
import pandas as pd
import yfinance as yf

from backend.config import settings


def _download_ohlcv(symbol: str, period: str, interval: str) -> pd.DataFrame:
    # auto_adjust=True set EXPLICITLY: returns split- and dividend-adjusted OHLC so a
    # split never looks like a price crash to the signal engine / backtest. Pinning it
    # guards against yfinance silently changing the default (corporate-actions safety).
    return yf.download(
        symbol,
        period=period,
        interval=interval,
        progress=False,
        threads=False,
        auto_adjust=True,
    )


async def fetch_ohlcv(symbol: str, period: str = "5d", interval: str = "1d") -> list[dict]:
    """Fetch OHLCV from yfinance without blocking the event loop."""
    symbol = symbol.upper()
    df = await asyncio.to_thread(_download_ohlcv, symbol, period, interval)
    if df.empty:
        return []

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    df = df.reset_index().rename(columns={
        "Date": "timestamp", "Datetime": "timestamp",
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    })
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"yfinance response missing columns: {sorted(missing)}")

    df = df.dropna(subset=list(required))
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.to_pydatetime()
    for column in ["open", "high", "low", "close"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")
    df = df.dropna(subset=list(required))
    df["timestamp"] = [
        ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        for ts in df["timestamp"]
    ]
    df["symbol"] = symbol
    return df[["symbol", "timestamp", "open", "high", "low", "close", "volume"]].to_dict("records")


async def fetch_finnhub_quote(symbol: str) -> dict | None:
    """Fetch real-time quote from Finnhub. Returns None if key not configured."""
    if not settings.finnhub_api_key:
        return None
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": symbol.upper(), "token": settings.finnhub_api_key},
        )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("c"):
        return None
    return {"symbol": symbol.upper(), "price": data["c"], "change_pct": data["dp"]}
