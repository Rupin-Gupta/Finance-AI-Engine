import pandas as pd
from fastapi import APIRouter, Depends
from datetime import datetime, timedelta, timezone

from backend.api.auth import require_api_key
from backend.api.validators import validate_symbol
from backend.dependencies import get_db
from backend.db.queries.market_data import get_ohlcv
from backend.db.queries.analytics import get_analytics, upsert_analytics
from backend.analytics.indicators import add_all_indicators

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/{symbol}")
async def get_analytics_endpoint(symbol: str, days: int = 60, conn=Depends(get_db)):
    sym = validate_symbol(symbol)
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)

    db_rows = await get_analytics(conn, sym, start, end)
    if db_rows:
        return {"symbol": sym, "data": [dict(r) for r in db_rows]}

    # No persisted analytics yet — compute, persist, return
    ohlcv_rows = await get_ohlcv(conn, sym, start, end)
    if not ohlcv_rows:
        return {"symbol": sym, "data": []}

    df = pd.DataFrame([dict(r) for r in ohlcv_rows]).sort_values("timestamp")
    df = add_all_indicators(df)
    analytics_rows = df[
        ["symbol", "timestamp", "sma_20", "ema_20", "rsi_14", "volatility_20", "momentum_10"]
    ].to_dict("records")
    await upsert_analytics(conn, analytics_rows)

    return {"symbol": sym, "data": analytics_rows}
