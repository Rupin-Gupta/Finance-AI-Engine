"""Market regime (R5): current Bull/Bear/High-Vol/Sideways classification per market."""
import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.dependencies import get_db
from backend.db.queries.regime import get_latest_regime, get_regime_history

router = APIRouter(dependencies=[Depends(require_api_key)])


def _f(v) -> float | None:
    return float(v) if v is not None else None


def _row_to_dict(row) -> dict | None:
    if not row:
        return None
    return {
        "date": str(row["date"]),
        "regime": row["regime"],
        "reason": row["reason"],
        "index_symbol": row["index_symbol"],
        "index_close": _f(row["index_close"]),
        "sma_50": _f(row["sma_50"]),
        "sma_200": _f(row["sma_200"]),
        "vix": _f(row["vix"]),
        "realized_vol": _f(row["realized_vol"]),
        "breadth_pct": _f(row["breadth_pct"]),
    }


@router.get("")
@limiter.limit("30/minute")
async def current_regime(request: Request, conn: asyncpg.Connection = Depends(get_db)) -> dict:
    """Latest classified regime for both markets (null until regime_run has run)."""
    us = await get_latest_regime(conn, "US")
    india = await get_latest_regime(conn, "INDIA")
    return {"us": _row_to_dict(us), "india": _row_to_dict(india)}


@router.get("/history")
@limiter.limit("30/minute")
async def regime_history(
    request: Request,
    market: str = Query(default="US"),
    days: int = Query(default=90, ge=7, le=730),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    market = market.strip().upper()
    if market not in ("US", "INDIA"):
        raise HTTPException(status_code=422, detail="market must be 'US' or 'INDIA'")
    rows = await get_regime_history(conn, market, days)
    return {
        "market": market,
        "history": [
            {
                "date": str(r["date"]),
                "regime": r["regime"],
                "reason": r["reason"],
                "index_close": _f(r["index_close"]),
                "vix": _f(r["vix"]),
                "realized_vol": _f(r["realized_vol"]),
                "breadth_pct": _f(r["breadth_pct"]),
            }
            for r in rows
        ],
    }
