"""Paper trading — virtual portfolio executed against real (latest) prices."""
from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.api.auth import require_api_key
from backend.api.validators import validate_symbol
from backend.config import settings
from backend.dependencies import get_db
from backend.db.queries.market_data import get_latest_prices
from backend.db.queries.paper import (
    get_or_create_portfolio, update_cash, get_positions, upsert_position,
    delete_position, insert_trade, list_trades, reset_portfolio, get_equity_history,
)
from backend.analytics.backtest import CostModel
from backend.analytics.paper_trading import execute_trade, portfolio_metrics, equity_curve_metrics

router = APIRouter(dependencies=[Depends(require_api_key)])


class TradeRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: float = Field(..., gt=0)

    @field_validator("symbol")
    @classmethod
    def _v(cls, v: str) -> str:
        return validate_symbol(v)


class ResetRequest(BaseModel):
    starting_cash: float | None = Field(default=None, gt=0)


def _f(v) -> float:
    return float(v) if v is not None else 0.0


def _positions_dict(rows) -> dict:
    return {r["symbol"]: {"quantity": _f(r["quantity"]), "avg_cost": _f(r["avg_cost"])} for r in rows}


@router.get("")
async def get_portfolio(conn: asyncpg.Connection = Depends(get_db)) -> dict:
    pf = await get_or_create_portfolio(conn, settings.paper_starting_cash)
    rows = await get_positions(conn)
    positions = _positions_dict(rows)
    prices = await get_latest_prices(conn, list(positions.keys()))

    metrics = portfolio_metrics(_f(pf["cash"]), positions, prices, _f(pf["starting_cash"]))
    enriched = []
    for sym, p in positions.items():
        last = prices.get(sym)
        mv = p["quantity"] * last if last is not None else None
        pnl = p["quantity"] * (last - p["avg_cost"]) if last is not None else None
        enriched.append({
            "symbol": sym,
            "quantity": p["quantity"],
            "avg_cost": round(p["avg_cost"], 4),
            "current_price": round(last, 2) if last is not None else None,
            "market_value": round(mv, 2) if mv is not None else None,
            "unrealized_pnl": round(pnl, 2) if pnl is not None else None,
        })
    return {"metrics": metrics, "positions": enriched}


@router.post("/trade")
async def place_trade(body: TradeRequest, conn: asyncpg.Connection = Depends(get_db)) -> dict:
    pf = await get_or_create_portfolio(conn, settings.paper_starting_cash)
    prices = await get_latest_prices(conn, [body.symbol])
    price = prices.get(body.symbol)
    if price is None:
        raise HTTPException(status_code=422, detail=f"No price data for {body.symbol} — ingest market data first.")

    rows = await get_positions(conn)
    positions = _positions_dict(rows)

    try:
        new_cash, new_positions, trade = execute_trade(
            _f(pf["cash"]), positions, body.side, body.symbol, body.quantity, price,
            cost_model=CostModel.for_symbol(body.symbol),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    async with conn.transaction():
        await update_cash(conn, new_cash)
        new_pos = new_positions.get(body.symbol)
        if new_pos:
            await upsert_position(conn, body.symbol, new_pos["quantity"], new_pos["avg_cost"])
        else:
            await delete_position(conn, body.symbol)
        await insert_trade(conn, trade)

    return {"trade": trade, "cash": new_cash}


@router.post("/reset")
async def reset(body: ResetRequest, conn: asyncpg.Connection = Depends(get_db)) -> dict:
    starting = body.starting_cash or settings.paper_starting_cash
    await reset_portfolio(conn, starting)
    return {"reset": True, "starting_cash": starting}


@router.get("/history")
async def equity_history(conn: asyncpg.Connection = Depends(get_db)) -> dict:
    """Equity-curve points + over-time risk/return metrics (R1.2)."""
    rows = await get_equity_history(conn)
    curve = [
        {"ts": str(r["ts"]), "equity": _f(r["equity"]), "cash": _f(r["cash"]),
         "positions_value": _f(r["positions_value"]),
         "total_return": float(r["total_return"]) if r["total_return"] is not None else None}
        for r in rows
    ]
    trade_rows = await list_trades(conn, limit=1000)
    metrics = equity_curve_metrics(curve, [dict(t) for t in trade_rows])
    return {"curve": curve, "metrics": metrics}


@router.get("/trades")
async def trades(conn: asyncpg.Connection = Depends(get_db)) -> dict:
    rows = await list_trades(conn)
    return {
        "trades": [
            {
                "ts": str(r["ts"]), "symbol": r["symbol"], "side": r["side"],
                "quantity": _f(r["quantity"]), "price": _f(r["price"]),
                "fee": _f(r["fee"]),
                "realized_pnl": float(r["realized_pnl"]) if r["realized_pnl"] is not None else None,
            }
            for r in rows
        ]
    }
