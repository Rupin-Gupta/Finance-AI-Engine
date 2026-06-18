"""Market-data reliability report (P9): consistency, outliers, staleness, source reconcile."""
from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.api.validators import validated_symbol
from backend.dependencies import get_db
from backend.db.queries.market_data import get_ohlcv
from backend.db.queries.corporate_actions import get_splits
from backend.ingest.market import fetch_finnhub_quote
from backend.analytics.data_quality import assess_data_quality

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/{symbol}")
@limiter.limit("30/minute")
async def data_quality(
    request: Request,
    sym: str = Depends(validated_symbol),
    days: int = Query(default=365, ge=30, le=1095),
    reconcile: bool = Query(default=True, description="Cross-check the latest close with a live quote"),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    now = datetime.now(tz=timezone.utc)
    rows = [dict(r) for r in await get_ohlcv(conn, sym, now - timedelta(days=days), now)]
    if not rows:
        raise HTTPException(status_code=404, detail=f"No stored data for {sym}.")

    split_dates = {str(d) for d, _ in await get_splits(conn, sym)}

    live_close = None
    if reconcile:
        quote = await fetch_finnhub_quote(sym)   # None for .NS/.BO (Finnhub gap) — skipped
        if quote:
            live_close = quote.get("price") or quote.get("close")

    report = assess_data_quality(rows, split_dates=split_dates, live_close=live_close, now=now)
    report["symbol"] = sym
    return report
