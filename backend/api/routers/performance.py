"""Recommendation accuracy: scores past BUY/SELL/HOLD calls against realized prices."""
from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, Query, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.api.validators import validate_symbol
from backend.dependencies import get_db
from backend.db.queries.decisions import get_decisions_since, get_decisions_with_signals_since
from backend.db.queries.market_data import get_closes_by_symbol
from backend.analytics.performance import (
    resolve_price, evaluate_decision, aggregate_performance,
)
from backend.analytics.calibration import score_for_calibration, decompose_decision

router = APIRouter(dependencies=[Depends(require_api_key)])


def _score_decisions(decisions: list, closes_by_symbol: dict, horizon_days: int, today) -> list[dict]:
    """Resolve entry/exit prices and score each decision. Pure — no I/O.

    Decisions whose horizon hasn't elapsed, or that lack price data, are skipped.
    """
    evaluated: list[dict] = []
    for d in decisions:
        sym = d["symbol"]
        series = closes_by_symbol.get(sym)
        if not series:
            continue

        created = d["created_at"]
        dec_date = created.date() if hasattr(created, "date") else created
        exit_target = dec_date + timedelta(days=horizon_days)
        if exit_target > today:
            continue  # horizon not elapsed yet — still pending

        entry = resolve_price(series, dec_date, "on_or_before")
        exit_ = resolve_price(series, exit_target, "on_or_after")
        scored = evaluate_decision(d["recommendation"], entry, exit_)
        if scored is None:
            continue

        evaluated.append({
            "symbol": sym,
            "recommendation": d["recommendation"],
            "risk_level": d["risk_level"],
            "confidence": float(d["confidence"]) if d["confidence"] is not None else None,
            "decision_date": str(dec_date),
            "entry_price": round(entry, 2),
            "exit_price": round(exit_, 2),
            **scored,
        })
    return evaluated


@router.get("")
@limiter.limit("30/minute")
async def get_performance(
    request: Request,
    symbol: str | None = Query(default=None, description="Filter to one symbol"),
    horizon_days: int = Query(default=5, ge=1, le=60, description="Days after each call to measure outcome"),
    lookback_days: int = Query(default=180, ge=30, le=730, description="How far back to score decisions"),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    sym = validate_symbol(symbol) if symbol else None
    now = datetime.now(tz=timezone.utc)
    decision_start = now - timedelta(days=lookback_days)

    decisions = await get_decisions_since(conn, decision_start, sym)
    symbols = sorted({d["symbol"] for d in decisions})

    # buffer back a few days so entry-price lookup finds the prior trading day
    price_start = decision_start - timedelta(days=10)
    closes = await get_closes_by_symbol(conn, symbols, price_start, now)

    evaluated = _score_decisions(decisions, closes, horizon_days, now.date())
    agg = aggregate_performance(evaluated)

    return {
        "symbol": sym,
        "horizon_days": horizon_days,
        "lookback_days": lookback_days,
        "evaluated_count": len(evaluated),
        "pending_count": len(decisions) - len(evaluated),
        **agg,
        "recent": evaluated[-25:][::-1],  # most recent first, capped
    }


@router.get("/attribution")
@limiter.limit("30/minute")
async def get_attribution(
    request: Request,
    symbol: str | None = Query(default=None, description="Filter to one symbol"),
    horizon_days: int = Query(default=5, ge=1, le=60),
    lookback_days: int = Query(default=90, ge=7, le=730),
    limit: int = Query(default=25, ge=1, le=100),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """R9: per-call return decomposition — which signals earned each closed call's return."""
    sym = validate_symbol(symbol) if symbol else None
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=lookback_days)

    decisions = await get_decisions_with_signals_since(conn, start, sym)
    symbols = sorted({d["symbol"] for d in decisions})
    closes = await get_closes_by_symbol(conn, symbols, start - timedelta(days=10), now)

    scored = score_for_calibration(decisions, closes, horizon_days, now.date())
    calls = [
        {
            "symbol": r["symbol"],
            "decision_date": r["decision_date"],
            "recommendation": r["recommendation"],
            "confidence": r["confidence"],
            "strategy_return": r["strategy_return"],
            "correct": r["correct"],
            "breakdown": decompose_decision(r),
        }
        for r in scored[::-1][:limit]  # most recent first
    ]
    return {
        "symbol": sym,
        "horizon_days": horizon_days,
        "lookback_days": lookback_days,
        "evaluated_count": len(scored),
        "calls": calls,
    }
