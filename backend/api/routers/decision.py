"""GET /v1/decision/{symbol} — full decision intelligence payload."""
import json
import logging
from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, Query, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.api.validators import validate_symbol
from backend.dependencies import get_db
from backend.db.queries.analytics import get_analytics
from backend.db.queries.market_data import get_ohlcv
from backend.db.queries.sentiment import get_latest_sentiment, get_sentiment_history
from backend.db.queries.decisions import (
    get_latest_decision, get_forecasts,
    upsert_decision, upsert_forecasts,
)
from backend.decision.signals import compute_all_signals
from backend.decision.engine import make_recommendation
from backend.decision.forecast import run_forecast
from backend.llm.client import get_llm_client
from backend.llm.prompts import build_decision_prompt

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_api_key)])

_CACHE_TTL_HOURS = 4


@router.get("/{symbol}")
@limiter.limit("20/minute")
async def get_decision(
    request: Request,
    symbol: str,
    force: bool = Query(default=False, description="Bypass cache and recompute"),
    conn: asyncpg.Connection = Depends(get_db),
):
    sym = validate_symbol(symbol)
    now = datetime.now(tz=timezone.utc)

    # --- staleness cache: return persisted decision if fresh ---
    if not force:
        cached = await get_latest_decision(conn, sym)
        if cached:
            age = now - cached["created_at"].replace(tzinfo=timezone.utc)
            if age < timedelta(hours=_CACHE_TTL_HOURS):
                try:
                    signals_json = json.loads(cached["signals_json"]) if isinstance(cached["signals_json"], str) else cached["signals_json"]
                except json.JSONDecodeError:
                    logger.warning("Corrupt signals_json for %s — recomputing", sym)
                    signals_json = {}
                forecast_rows = await get_forecasts(conn, sym, days=7)
                hist = await get_sentiment_history(conn, sym, days=30)
                sentiment_row = await get_latest_sentiment(conn, sym)
                return _build_response(sym, cached, signals_json, forecast_rows, hist, sentiment_row, cached=True)

    start = now - timedelta(days=90)

    # --- analytics ---
    analytics_rows = await get_analytics(conn, sym, start, now)
    latest = analytics_rows[-1] if analytics_rows else None

    rsi = sma_20 = momentum_10 = vol_20 = close = None
    if latest:
        rsi        = _f(latest, "rsi_14")
        sma_20     = _f(latest, "sma_20")
        momentum_10 = _f(latest, "momentum_10")
        vol_20     = _f(latest, "volatility_20")

    # get current close from market_data
    ohlcv_rows = await get_ohlcv(conn, sym, start, now)
    if ohlcv_rows:
        close = float(ohlcv_rows[-1]["close"])

    # --- sentiment ---
    sentiment_row = await get_latest_sentiment(conn, sym)
    sentiment_score = float(sentiment_row["score"]) if sentiment_row else None

    # --- forecast ---
    forecast_rows = await get_forecasts(conn, sym, days=7)
    predicted_close = None
    if forecast_rows:
        predicted_close = float(forecast_rows[0]["predicted_close"])
    elif ohlcv_rows:
        raw = [{"timestamp": r["timestamp"], "close": float(r["close"])} for r in ohlcv_rows]
        new_forecasts = await run_forecast(sym, raw, horizon_days=7)
        if new_forecasts:
            await upsert_forecasts(conn, new_forecasts)
            forecast_rows = await get_forecasts(conn, sym, days=7)
            predicted_close = float(forecast_rows[0]["predicted_close"]) if forecast_rows else None

    # --- signals + engine ---
    signals = compute_all_signals(close, rsi, sma_20, momentum_10, vol_20, sentiment_score, predicted_close)
    result = make_recommendation(signals, vol_20)

    # --- LLM explanation ---
    explanation = ""
    try:
        llm = get_llm_client()
        prompt = build_decision_prompt(
            symbol=sym,
            recommendation=result["recommendation"],
            confidence=result["confidence"],
            risk_level=result["risk_level"],
            signals_json=result["signals_json"],
            sentiment_score=sentiment_score,
            predicted_close=predicted_close,
            current_close=close,
        )
        explanation = await llm.complete(prompt)
    except Exception as exc:
        logger.warning("LLM explanation failed for %s: %s", sym, exc)

    # --- persist ---
    decision_row = {
        "symbol": sym,
        "recommendation": result["recommendation"],
        "confidence": result["confidence"],
        "signals_json": result["signals_json"],
        "risk_level": result["risk_level"],
        "explanation": explanation,
    }
    await upsert_decision(conn, decision_row)

    hist = await get_sentiment_history(conn, sym, days=30)
    return _build_response(sym, {**result, "explanation": explanation, "current_close": close},
                           result["signals_json"], forecast_rows, hist, sentiment_row, cached=False)


def _f(row, key: str) -> float | None:
    v = row[key]
    return float(v) if v is not None else None


def _build_response(sym, data, signals_json, forecast_rows, hist, sentiment_row, *, cached: bool) -> dict:
    return {
        "symbol": sym,
        "cached": cached,
        "recommendation": data["recommendation"],
        "confidence": float(data["confidence"]),
        "risk_level": data["risk_level"],
        "weighted_score": float(data.get("weighted_score", 0)),
        "signals": signals_json,
        "forecast": [
            {
                "date": str(r["forecast_date"]),
                "predicted_close": float(r["predicted_close"]),
                "lower": float(r["lower_bound"]),
                "upper": float(r["upper_bound"]),
            }
            for r in forecast_rows
        ],
        "sentiment_score": float(sentiment_row["score"]) if sentiment_row else None,
        "sentiment_history": [
            {"date": str(r["date"]), "score": float(r["score"]), "headline_count": r["headline_count"]}
            for r in hist
        ],
        "current_close": data.get("current_close"),
        "explanation": data.get("explanation", ""),
    }
