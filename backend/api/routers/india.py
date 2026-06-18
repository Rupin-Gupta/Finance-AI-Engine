"""India market signals (P5): FII/DII flow, NIFTY PCR, Gift Nifty + the engine overlay score."""
import asyncpg
from fastapi import APIRouter, Depends, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.api.validators import validated_symbol
from backend.dependencies import get_db
from backend.db.queries.india_signals import (
    get_latest_market_signals, market_context, get_bulk_deals,
)
from backend.decision.india_signals import score_india_market

router = APIRouter(dependencies=[Depends(require_api_key)])


def _f(v):
    return float(v) if v is not None else None


@router.get("/signals")
@limiter.limit("30/minute")
async def india_signals(request: Request, conn: asyncpg.Connection = Depends(get_db)) -> dict:
    """Latest India market signals + the composite `india_flow` overlay score (applied to .NS/.BO)."""
    row = await get_latest_market_signals(conn)
    ctx = market_context(row)
    sig = score_india_market(ctx)
    return {
        "date": str(row["date"]) if row else None,
        "fii_net_cr": _f(row["fii_net_cr"]) if row else None,
        "dii_net_cr": _f(row["dii_net_cr"]) if row else None,
        "pcr": _f(row["pcr"]) if row else None,
        "gift_nifty_pct": _f(row["gift_nifty_pct"]) if row else None,
        "source": row["source"] if row else None,
        "india_flow": {"score": sig.score, "weight": sig.weight,
                       "value": sig.value, "label": sig.label},
    }


@router.get("/deals/{symbol}")
@limiter.limit("30/minute")
async def india_deals(request: Request, sym: str = Depends(validated_symbol),
                      conn: asyncpg.Connection = Depends(get_db)) -> dict:
    """Recent bulk/block deals for a symbol (informational)."""
    rows = await get_bulk_deals(conn, sym)
    return {
        "symbol": sym,
        "deals": [
            {"date": str(r["deal_date"]), "client": r["client"], "side": r["side"],
             "quantity": r["quantity"], "price": _f(r["price"]), "type": r["deal_type"]}
            for r in rows
        ],
    }
