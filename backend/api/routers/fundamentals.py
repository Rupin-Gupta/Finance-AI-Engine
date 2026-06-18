from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import require_api_key
from backend.api.validators import validated_symbol
from backend.dependencies import get_db
from backend.analytics.fundamentals import fetch_fundamentals, fetch_earnings
from backend.db.queries.fundamentals import (
    get_fundamentals,
    upsert_fundamentals,
    get_earnings,
    upsert_earnings,
)
from backend.db.queries.stocks import ensure_stocks, update_stock_names, update_stock_sectors

router = APIRouter(dependencies=[Depends(require_api_key)])

_STALE_AFTER_HOURS = 24


@router.get("/{symbol}")
async def get_fundamentals_endpoint(sym: str = Depends(validated_symbol), conn=Depends(get_db)):
    db_row = await get_fundamentals(conn, sym)
    stale_cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=_STALE_AFTER_HOURS)

    if db_row and db_row["updated_at"] > stale_cutoff:
        earnings_rows = await get_earnings(conn, sym)
        return {
            "symbol": sym,
            "fundamentals": _fmt_fundamentals(db_row),
            "earnings": [dict(r) for r in earnings_rows],
        }

    await ensure_stocks(conn, [sym])

    try:
        fund_data = await fetch_fundamentals(sym)
        earnings_data = await fetch_earnings(sym)
    except Exception as exc:
        if db_row:
            earnings_rows = await get_earnings(conn, sym)
            return {
                "symbol": sym,
                "fundamentals": _fmt_fundamentals(db_row),
                "earnings": [dict(r) for r in earnings_rows],
                "warning": f"Could not refresh from yfinance: {exc}",
            }
        raise HTTPException(status_code=502, detail=f"Failed to fetch fundamentals for {sym}: {exc}")

    await upsert_fundamentals(conn, fund_data)
    if fund_data.get("name"):
        await update_stock_names(conn, {sym: fund_data["name"]})
    if fund_data.get("sector"):
        await update_stock_sectors(conn, {sym: fund_data["sector"]})
    if earnings_data:
        await upsert_earnings(conn, earnings_data)

    earnings_rows = await get_earnings(conn, sym)
    return {
        "symbol": sym,
        "fundamentals": _fmt_fundamentals(fund_data),
        "earnings": [dict(r) for r in earnings_rows],
    }


def _fmt_fundamentals(row) -> dict:
    data = dict(row) if hasattr(row, "keys") else row
    data.pop("symbol", None)
    for k, v in data.items():
        if hasattr(v, "isoformat"):
            data[k] = v.isoformat()
    return data
