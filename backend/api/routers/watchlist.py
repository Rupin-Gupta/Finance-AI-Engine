"""Watchlist + live P&L: persisted symbols enriched with price, P&L, decision, sentiment."""
import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.api.auth import require_api_key
from backend.api.validators import validate_symbol, validated_symbol
from backend.dependencies import get_db
from backend.db.queries.watchlist import (
    upsert_watchlist_item, list_watchlist, delete_watchlist_item,
)
from backend.db.queries.market_data import get_latest_prices
from backend.db.queries.decisions import get_latest_decisions_multi
from backend.db.queries.sentiment import get_latest_sentiment_multi
from backend.db.queries.calibration_summary import get_calibration_summary
from backend.analytics.sizing import recommend_size
from backend.analytics.calibration import lookup_calibrated_prob

router = APIRouter(dependencies=[Depends(require_api_key)])


class WatchlistItem(BaseModel):
    symbol: str
    quantity: float | None = Field(default=None, ge=0)
    cost_basis: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=280)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        return validate_symbol(v)


def _f(v) -> float | None:
    return float(v) if v is not None else None


def _suggested_pct(dec: dict | None, calibration: dict | None) -> float | None:
    """Position-size suggestion for a watched name (R2.2): Kelly/vol/risk-budget sizing
    from the latest decision, using the calibrated hit rate as win prob when available."""
    if not dec or not dec.get("recommendation"):
        return None
    conf = _f(dec.get("confidence"))
    win_prob = None
    if calibration:
        bins = (calibration.get("reliability") or {}).get("bins") or []
        win_prob = lookup_calibrated_prob(bins, conf, fallback=conf)
    return recommend_size(conf, None, dec.get("risk_level"), win_prob=win_prob)["recommended_pct"]


def _enrich(
    items: list,
    prices: dict[str, float],
    decisions: dict,
    sentiment: dict[str, float],
    calibration: dict | None = None,
) -> tuple[list[dict], dict]:
    """Pure enrichment: join persisted items with live price/decision/sentiment and
    compute per-position + portfolio-level P&L. No I/O — unit-testable."""
    enriched: list[dict] = []
    total_market_value = 0.0
    total_cost_value = 0.0

    for it in items:
        sym = it["symbol"]
        qty = _f(it["quantity"])
        cost_basis = _f(it["cost_basis"])
        price = prices.get(sym)

        market_value = qty * price if (qty is not None and price is not None) else None
        cost_value = qty * cost_basis if (qty is not None and cost_basis is not None) else None

        unrealized_pnl = None
        unrealized_pnl_pct = None
        if cost_basis is not None and price is not None:
            unrealized_pnl_pct = round((price - cost_basis) / cost_basis, 4) if cost_basis else None
        if market_value is not None and cost_value is not None:
            unrealized_pnl = round(market_value - cost_value, 2)
            total_market_value += market_value
            total_cost_value += cost_value

        dec = decisions.get(sym)
        enriched.append({
            "symbol": sym,
            "quantity": qty,
            "cost_basis": cost_basis,
            "note": it["note"],
            "current_price": round(price, 2) if price is not None else None,
            "market_value": round(market_value, 2) if market_value is not None else None,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "recommendation": dec["recommendation"] if dec else None,
            "confidence": _f(dec["confidence"]) if dec else None,
            "risk_level": dec["risk_level"] if dec else None,
            "suggested_position_pct": _suggested_pct(dec, calibration),
            "sentiment_score": sentiment.get(sym),
        })

    total_pnl = round(total_market_value - total_cost_value, 2) if total_cost_value else 0.0
    total_pnl_pct = round((total_market_value - total_cost_value) / total_cost_value, 4) if total_cost_value else None
    totals = {
        "positions": len(items),
        "market_value": round(total_market_value, 2),
        "cost_value": round(total_cost_value, 2),
        "unrealized_pnl": total_pnl,
        "unrealized_pnl_pct": total_pnl_pct,
    }
    return enriched, totals


@router.get("")
async def get_watchlist(conn: asyncpg.Connection = Depends(get_db)) -> dict:
    items = await list_watchlist(conn)
    symbols = [r["symbol"] for r in items]

    prices = await get_latest_prices(conn, symbols)
    decisions = await get_latest_decisions_multi(conn, symbols)
    sentiment = await get_latest_sentiment_multi(conn, symbols)
    calibration = await get_calibration_summary(conn, horizon_days=5)

    enriched, totals = _enrich(items, prices, decisions, sentiment, calibration)
    return {"items": enriched, "totals": totals}


@router.post("")
async def add_watchlist_item(
    body: WatchlistItem, conn: asyncpg.Connection = Depends(get_db)
) -> dict:
    row = await upsert_watchlist_item(conn, body.model_dump())
    return {
        "symbol": row["symbol"],
        "quantity": _f(row["quantity"]),
        "cost_basis": _f(row["cost_basis"]),
        "note": row["note"],
    }


@router.delete("/{symbol}")
async def remove_watchlist_item(
    sym: str = Depends(validated_symbol), conn: asyncpg.Connection = Depends(get_db)
) -> dict:
    removed = await delete_watchlist_item(conn, sym)
    if not removed:
        raise HTTPException(status_code=404, detail=f"{sym} not in watchlist")
    return {"removed": sym}
