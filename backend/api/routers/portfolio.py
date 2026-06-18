from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.api.validators import validate_symbol
from backend.dependencies import get_db
from backend.db.queries.market_data import (
    get_prices_multi, get_latest_prices, get_high_water, get_latest_volatility,
)
from backend.db.queries.watchlist import list_watchlist
from backend.db.queries.paper import get_positions
from backend.db.queries.stocks import get_symbol_sectors
from backend.db.queries.fundamentals import get_market_caps
from backend.db.queries.decisions import get_latest_decisions_multi
from backend.db.queries.stops import get_stop_configs, upsert_stop_config
from backend.analytics.portfolio_risk import assess_portfolio_risk
from backend.analytics.portfolio import optimize_portfolio_async
from backend.analytics.stops import position_stop

router = APIRouter(dependencies=[Depends(require_api_key)])


def _f(v) -> float | None:
    return float(v) if v is not None else None


class OptimizeRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=2, max_length=30)
    objective: Literal["min_variance", "max_sharpe", "efficient_frontier"] = "max_sharpe"
    risk_free_rate: float = Field(default=0.05, ge=0.0, le=0.20)
    lookback_days: int = Field(default=365, ge=60, le=730)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v):
        return [validate_symbol(s) for s in v]


@router.post("/optimize")
async def portfolio_optimize(body: OptimizeRequest, conn=Depends(get_db)):
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=body.lookback_days)

    prices = await get_prices_multi(conn, body.symbols, start, end)

    if prices.empty:
        raise HTTPException(
            status_code=422,
            detail="No price data found for the requested symbols. Ingest market data first.",
        )

    missing = [s for s in body.symbols if s not in prices.columns]
    available = list(prices.columns)

    if len(available) < 2:
        raise HTTPException(
            status_code=422,
            detail=f"Need at least 2 symbols with sufficient data. Available: {available}",
        )

    try:
        result = await optimize_portfolio_async(prices, body.objective, body.risk_free_rate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "symbols": available,
        "objective": body.objective,
        "risk_free_rate": body.risk_free_rate,
        "lookback_days": body.lookback_days,
        "missing_symbols": missing,
        **result,
    }


@router.get("/risk")
async def portfolio_risk(
    source: Literal["watchlist", "paper"] = "watchlist",
    lookback_days: int = Query(default=365, ge=60, le=730),
    confidence: float = Query(default=0.95, ge=0.80, le=0.99),
    conn=Depends(get_db),
):
    """R6: concentration / correlation / VaR report for the watchlist or paper book."""
    if source == "watchlist":
        rows = await list_watchlist(conn)
        holdings = [(r["symbol"], float(r["quantity"])) for r in rows if r["quantity"]]
    else:
        rows = await get_positions(conn)
        holdings = [(r["symbol"], float(r["quantity"])) for r in rows if r["quantity"]]

    if not holdings:
        raise HTTPException(
            status_code=422,
            detail=f"No {source} positions with a quantity — nothing to assess.",
        )

    symbols = [s for s, _ in holdings]
    latest = await get_latest_prices(conn, symbols)
    positions = [
        {"symbol": s, "value": qty * latest[s]}
        for s, qty in holdings if s in latest
    ]
    if not positions:
        raise HTTPException(
            status_code=422,
            detail="No stored prices for any held symbol — run market ingest first.",
        )

    sector_map = await get_symbol_sectors(conn, symbols)
    cap_map = await get_market_caps(conn, symbols)
    end = datetime.now(tz=timezone.utc)
    prices = await get_prices_multi(conn, symbols, end - timedelta(days=lookback_days), end)

    result = assess_portfolio_risk(positions, sector_map, cap_map, prices, confidence=confidence)
    result["source"] = source
    result["lookback_days"] = lookback_days
    missing = sorted(set(symbols) - {p["symbol"] for p in positions})
    if missing:
        result.setdefault("warnings", []).append(f"No price data for: {missing} — excluded.")
    return result


class StopConfig(BaseModel):
    stop_pct: float | None = Field(default=None, gt=0, le=0.5)
    trailing: bool = True


@router.get("/stops")
async def portfolio_stops(
    source: Literal["watchlist", "paper"] = "watchlist",
    lookback_days: int = Query(default=90, ge=20, le=365),
    conn=Depends(get_db),
):
    """P3: stop-loss / trailing-stop monitor for held positions + breach summary.

    entry = cost_basis (watchlist) / avg_cost (paper); trailing reference = high-water
    over the lookback; stop width is vol-derived + risk-trimmed unless overridden per symbol.
    """
    if source == "watchlist":
        rows = await list_watchlist(conn)
        holdings = [(r["symbol"], _f(r["cost_basis"])) for r in rows if r["cost_basis"]]
    else:
        rows = await get_positions(conn)
        holdings = [(r["symbol"], _f(r["avg_cost"])) for r in rows if r["avg_cost"]]

    symbols = [s for s, _ in holdings]
    if not symbols:
        return {"source": source, "positions": [], "breached_count": 0,
                "warnings": [f"No {source} positions with an entry price."]}

    prices = await get_latest_prices(conn, symbols)
    highs = await get_high_water(conn, symbols, days=lookback_days)
    vols = await get_latest_volatility(conn, symbols)
    decisions = await get_latest_decisions_multi(conn, symbols)
    configs = await get_stop_configs(conn, symbols)

    positions = []
    breached = 0
    for sym, entry in holdings:
        cfg = configs.get(sym, {})
        dec = decisions.get(sym)
        stop = position_stop(
            entry=entry,
            current=prices.get(sym),
            high_water=highs.get(sym),
            vol_20=vols.get(sym),
            risk_level=dec["risk_level"] if dec else None,
            stop_pct=cfg.get("stop_pct"),
            trailing=cfg.get("trailing", True),
        )
        if stop is None:
            continue
        if stop["breached"]:
            breached += 1
        positions.append({"symbol": sym, "entry": round(entry, 4), **stop})

    positions.sort(key=lambda p: p["distance_pct"] if p["distance_pct"] is not None else 1.0)
    return {
        "source": source,
        "lookback_days": lookback_days,
        "positions": positions,
        "breached_count": breached,
        "breached": [p["symbol"] for p in positions if p["breached"]],
    }


@router.put("/stops/{symbol}")
async def set_stop(symbol: str, body: StopConfig, conn=Depends(get_db)):
    """Set or override a symbol's stop config (stop_pct None → revert to recommended)."""
    sym = validate_symbol(symbol)
    await upsert_stop_config(conn, sym, body.stop_pct, body.trailing)
    return {"symbol": sym, "stop_pct": body.stop_pct, "trailing": body.trailing}
