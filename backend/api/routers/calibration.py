"""Confidence calibration + signal edge + threshold tuning — closes the ML feedback loop."""
from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, Query, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.api.validators import validate_symbol
from backend.dependencies import get_db
from backend.db.queries.decisions import get_decisions_with_signals_since
from backend.db.queries.market_data import get_closes_by_symbol
from backend.db.queries.signal_performance import get_signal_history, get_signal_rollup
from backend.analytics.calibration import (
    reliability_curve, signal_contribution, tune_thresholds,
    score_for_calibration, weighted_score_from_signals,
)
from backend.analytics.drift import model_health
from backend.decision.engine import BUY_THRESHOLD

router = APIRouter(dependencies=[Depends(require_api_key)])

# Back-compat aliases (kept for existing tests / readability).
_score_for_calibration = score_for_calibration
_weighted_score = weighted_score_from_signals


@router.get("")
@limiter.limit("30/minute")
async def get_calibration(
    request: Request,
    symbol: str | None = Query(default=None),
    horizon_days: int = Query(default=5, ge=1, le=60),
    lookback_days: int = Query(default=180, ge=30, le=730),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    sym = validate_symbol(symbol) if symbol else None
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=lookback_days)

    decisions = await get_decisions_with_signals_since(conn, start, sym)
    symbols = sorted({d["symbol"] for d in decisions})
    closes = await get_closes_by_symbol(conn, symbols, start - timedelta(days=10), now)

    scored = _score_for_calibration(decisions, closes, horizon_days, now.date())

    return {
        "symbol": sym,
        "horizon_days": horizon_days,
        "lookback_days": lookback_days,
        "evaluated_count": len(scored),
        "reliability": reliability_curve(scored),
        "signals": signal_contribution(scored),
        "threshold_tuning": tune_thresholds(scored, current_threshold=BUY_THRESHOLD),
    }


@router.get("/history")
@limiter.limit("30/minute")
async def get_signal_performance_history(
    request: Request,
    signal: str | None = Query(default=None, description="Filter to one signal name"),
    days: int = Query(default=180, ge=7, le=730),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Per-signal accuracy + return-attribution snapshots over time (written by signal_snapshot_run)."""
    rows = await get_signal_history(conn, signal, days)
    return {
        "signal": signal,
        "days": days,
        "history": [
            {
                "date": str(r["snapshot_date"]),
                "signal": r["signal"],
                "active_count": r["active_count"],
                "accuracy": float(r["accuracy"]) if r["accuracy"] is not None else None,
                "attributed_return": float(r["attributed_return"]) if r["attributed_return"] is not None else None,
                "avg_weight": float(r["avg_weight"]) if r["avg_weight"] is not None else None,
            }
            for r in rows
        ],
    }


@router.get("/rollup")
@limiter.limit("30/minute")
async def get_signal_rollup_endpoint(
    request: Request,
    days: int = Query(default=365, ge=30, le=1095, description="Trailing window (default 12 months)"),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Trailing-window (default 12-month) per-signal rollup of accuracy + return attribution (R3.1)."""
    rows = await get_signal_rollup(conn, days)
    return {
        "days": days,
        "signals": [
            {
                "signal": r["signal"],
                "snapshots": r["snapshots"],
                "avg_accuracy": float(r["avg_accuracy"]) if r["avg_accuracy"] is not None else None,
                "total_attributed_return": float(r["total_attributed_return"]) if r["total_attributed_return"] is not None else None,
                "avg_attributed_return": float(r["avg_attributed_return"]) if r["avg_attributed_return"] is not None else None,
                "avg_weight": float(r["avg_weight"]) if r["avg_weight"] is not None else None,
                "total_active": r["total_active"],
            }
            for r in rows
        ],
    }


@router.get("/drift")
@limiter.limit("30/minute")
async def get_model_drift(
    request: Request,
    horizon_days: int = Query(default=5, ge=1, le=60),
    lookback_days: int = Query(default=180, ge=30, le=730),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """R7: model health — rolling accuracy, drift verdict, per-signal edge trend."""
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=lookback_days)

    decisions = await get_decisions_with_signals_since(conn, start)
    symbols = sorted({d["symbol"] for d in decisions})
    closes = await get_closes_by_symbol(conn, symbols, start - timedelta(days=10), now)
    scored = score_for_calibration(decisions, closes, horizon_days, now.date())

    history = [dict(r) for r in await get_signal_history(conn, days=lookback_days)]
    health = model_health(scored, history)
    return {
        "horizon_days": horizon_days,
        "lookback_days": lookback_days,
        "evaluated_count": len(scored),
        **health,
    }
