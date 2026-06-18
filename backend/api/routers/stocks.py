from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import require_api_key
from backend.api.validators import validated_symbol
from backend.dependencies import get_db
from backend.ingest.market import fetch_finnhub_quote
from backend.db.queries.market_data import get_ohlcv

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/{symbol}/quote")
async def get_quote(sym: str = Depends(validated_symbol), conn=Depends(get_db)):
    quote = await fetch_finnhub_quote(sym)
    if quote:
        return quote

    # Finnhub unavailable — return latest close from DB
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=7)
    rows = await get_ohlcv(conn, sym, start, end)
    if rows:
        latest = rows[-1]
        return {
            "symbol": sym,
            "source": "db_cache",
            "close": float(latest["close"]),
            "timestamp": latest["timestamp"].isoformat(),
        }
    raise HTTPException(status_code=404, detail=f"No quote data available for {sym}")


@router.get("/{symbol}/ohlcv")
async def get_ohlcv_endpoint(sym: str = Depends(validated_symbol), days: int = 30, conn=Depends(get_db)):
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)
    rows = await get_ohlcv(conn, sym, start, end)
    return [dict(r) for r in rows]
