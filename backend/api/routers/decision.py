"""GET /v1/decision/{symbol} — full decision intelligence payload."""
import json
import logging
from datetime import datetime, timedelta, timezone

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.api.validators import validated_symbol
from backend.dependencies import get_db
from backend.db.queries.analytics import get_analytics
from backend.db.queries.market_data import get_ohlcv, get_latest_prices
from backend.db.queries.sentiment import (
    get_latest_sentiment, get_sentiment_history, get_sentiment_sources,
    get_sentiment_by_date_range,
)
from backend.db.queries.decisions import (
    get_latest_decision, get_forecasts,
    upsert_decision, upsert_forecasts, set_decision_committee,
)
from backend.db.queries.fundamentals import get_earnings, get_fundamentals
from backend.db.queries.signal_weights import get_active_weights
from backend.db.queries.calibration_summary import get_calibration_summary
from backend.db.queries.india_signals import get_latest_market_signals, market_context
from backend.db.queries.regime import get_latest_regime
from backend.db.queries.events import get_upcoming_events
from backend.analytics.regime import market_for_symbol, regime_adjusted_weights
from backend.analytics.events import nearest_gating_event
from backend.decision.signals import compute_all_signals, SIGNAL_WEIGHTS
from backend.decision.engine import make_recommendation
from backend.decision.forecast import run_forecast
from backend.ingest.market import fetch_ohlcv
from backend.analytics.backtest import run_backtest, CostModel
from backend.analytics.sizing import recommend_size
from backend.analytics.calibration import lookup_calibrated_prob
from backend.analytics.timeframes import multi_timeframe_view
from backend.ml.inference import predict_symbol_prob
from backend.llm.multi_agent import run_bull_bear_synthesis
from backend.llm.committee import run_committee

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_api_key)])

_CACHE_TTL_HOURS = 4


@router.get("/backtest/{symbol}")
@limiter.limit("5/minute")
async def backtest_decision(
    request: Request,
    sym: str = Depends(validated_symbol),
    days: int = Query(default=365, ge=30, le=730, description="Look-back window in days"),
    hold_days: int = Query(default=1, ge=1, le=20, description="Bars to hold each trade"),
    capital: float | None = Query(default=None, gt=0, description="Capital base → discrete, position-constrained mode"),
    position_fraction: float = Query(default=1.0, gt=0, le=1.0, description="Fraction of equity risked per trade"),
    conn: asyncpg.Connection = Depends(get_db),
):
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=days)

    analytics_rows = await get_analytics(conn, sym, start, now)
    if len(analytics_rows) < 10:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient analytics data for {sym} — run market ingest + analytics job first.",
        )

    ohlcv_rows = await get_ohlcv(conn, sym, start, now)
    sentiment_by_date = await get_sentiment_by_date_range(
        conn, sym, start.date(), now.date()
    )

    result = run_backtest(
        analytics_rows, ohlcv_rows, sentiment_by_date,
        cost_model=CostModel.for_symbol(sym),
        hold_days=hold_days, capital=capital, position_fraction=position_fraction,
    )
    result["symbol"] = sym
    result["window_days"] = days
    return result


@router.get("/{symbol}")
@limiter.limit("20/minute")
async def get_decision(
    request: Request,
    sym: str = Depends(validated_symbol),
    force: bool = Query(default=False, description="Bypass cache and recompute"),
    conn: asyncpg.Connection = Depends(get_db),
):
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
                    signals_json = None
                if signals_json is not None:
                    forecast_rows = await get_forecasts(conn, sym, days=7)
                    hist = await get_sentiment_history(conn, sym, days=30)
                    sentiment_row = await get_latest_sentiment(conn, sym)
                    source_rows = await get_sentiment_sources(conn, sym)
                    calibration = await get_calibration_summary(conn, horizon_days=5)
                    region = market_for_symbol(sym)
                    regime_row = await get_latest_regime(conn, region)
                    event_rows = await get_upcoming_events(conn, days=14, region=region)
                    event_ctx = nearest_gating_event([dict(r) for r in event_rows], now.date(), region)
                    return _build_response(sym, cached, signals_json, forecast_rows, hist, sentiment_row, source_rows, cached=True, calibration=calibration,
                                           regime=regime_row["regime"] if regime_row else None, event_context=event_ctx)

    start = now - timedelta(days=90)

    # --- analytics ---
    analytics_rows = await get_analytics(conn, sym, start, now)
    latest = analytics_rows[-1] if analytics_rows else None

    rsi = sma_20 = momentum_10 = vol_20 = close = ema_9 = ema_20 = None
    if latest:
        rsi         = _f(latest, "rsi_14")
        sma_20      = _f(latest, "sma_20")
        momentum_10 = _f(latest, "momentum_10")
        vol_20      = _f(latest, "volatility_20")
        ema_9       = _f(latest, "ema_9")
        ema_20      = _f(latest, "ema_20")

    # get current close + volume ratio from market_data
    ohlcv_rows = await get_ohlcv(conn, sym, start, now)
    volume_ratio = None
    if ohlcv_rows:
        close = float(ohlcv_rows[-1]["close"])
        vols = [float(r["volume"]) for r in ohlcv_rows if r.get("volume") is not None]
        if len(vols) >= 20:
            avg_vol = sum(vols[-20:]) / 20
            if avg_vol > 0:
                volume_ratio = vols[-1] / avg_vol

    # --- sentiment --- (aggregate can return a row with NULL score when counts sum to 0)
    sentiment_row = await get_latest_sentiment(conn, sym)
    sentiment_score = float(sentiment_row["score"]) if sentiment_row and sentiment_row["score"] is not None else None

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

    # --- earnings proximity ---
    days_to_earnings = None
    try:
        earnings_rows = await get_earnings(conn, sym, limit=5)
        today = now.date()
        for er in earnings_rows:
            ed = er["earnings_date"]
            if hasattr(ed, "date"):
                ed = ed.date()
            delta = (ed - today).days
            if delta >= 0:
                days_to_earnings = delta
                break
    except Exception:
        pass

    # --- India market overlay (P5): only for .NS/.BO symbols ---
    india_context = None
    if sym.endswith(".NS") or sym.endswith(".BO"):
        india_context = market_context(await get_latest_market_signals(conn))

    # --- signals + engine (auto-tuned weights, tilted by the market regime — R4 + R5) ---
    active_weights = await get_active_weights(conn)
    region = market_for_symbol(sym)
    regime_row = await get_latest_regime(conn, region)
    regime = regime_row["regime"] if regime_row else None
    weights = regime_adjusted_weights(active_weights or SIGNAL_WEIGHTS, regime) if regime else active_weights
    # R8: macro-event proximity gate for this symbol's market
    event_rows = await get_upcoming_events(conn, days=14, region=region)
    event_ctx = nearest_gating_event([dict(r) for r in event_rows], now.date(), region)
    # P14: ML directional probability (None unless a promoted model exists)
    ml_prob = await predict_symbol_prob(conn, latest, close, sentiment_score)
    signals = compute_all_signals(
        close, rsi, sma_20, momentum_10, vol_20, sentiment_score, predicted_close,
        ema_9=ema_9, ema_20=ema_20, volume_ratio=volume_ratio, weights=weights,
        india_context=india_context, ml_prob=ml_prob,
    )
    result = make_recommendation(signals, vol_20, days_to_earnings=days_to_earnings,
                                 regime=regime, event_context=event_ctx)

    # --- multi-agent LLM explanation (Bull + Bear parallel, then Synthesis) ---
    bull_case = bear_case = explanation = ""
    try:
        agent_result = await run_bull_bear_synthesis(
            symbol=sym,
            recommendation=result["recommendation"],
            confidence=result["confidence"],
            risk_level=result["risk_level"],
            signals_json=result["signals_json"],
            sentiment_score=sentiment_score,
            predicted_close=predicted_close,
            current_close=close,
            days_to_earnings=days_to_earnings,
        )
        bull_case  = agent_result["bull"]
        bear_case  = agent_result["bear"]
        explanation = agent_result["synthesis"]
    except Exception as exc:
        logger.warning("Multi-agent explanation failed for %s: %s", sym, exc)

    # --- persist ---
    decision_row = {
        "symbol": sym,
        "recommendation": result["recommendation"],
        "confidence": result["confidence"],
        "signals_json": result["signals_json"],
        "risk_level": result["risk_level"],
        "explanation": explanation,
        "bull_case": bull_case,
        "bear_case": bear_case,
    }
    await upsert_decision(conn, decision_row)

    hist = await get_sentiment_history(conn, sym, days=30)
    source_rows = await get_sentiment_sources(conn, sym)
    calibration = await get_calibration_summary(conn, horizon_days=5)
    return _build_response(
        sym,
        {
            **result,
            "explanation": explanation,
            "bull_case": bull_case,
            "bear_case": bear_case,
            "current_close": close,
            "days_to_earnings": days_to_earnings,
        },
        result["signals_json"], forecast_rows, hist, sentiment_row, source_rows, cached=False,
        calibration=calibration, regime=regime, event_context=event_ctx,
    )


def _f(row, key: str) -> float | None:
    v = row[key]
    return float(v) if v is not None else None


def _build_response(sym, data, signals_json, forecast_rows, hist, sentiment_row, source_rows, *, cached: bool, calibration: dict | None = None, regime: str | None = None, event_context: dict | None = None) -> dict:
    # Position sizing from confidence + volatility (signal value) + risk level.
    vol_val = None
    vsig = signals_json.get("volatility") if isinstance(signals_json, dict) else None
    if isinstance(vsig, dict):
        vol_val = vsig.get("value")

    # R2.1: use the calibrated hit rate (empirical accuracy at this confidence) as the
    # Kelly win probability when available, instead of the raw engine confidence.
    win_prob = None
    if calibration:
        bins = (calibration.get("reliability") or {}).get("bins") or []
        win_prob = lookup_calibrated_prob(bins, data["confidence"], fallback=data["confidence"])
    sizing = recommend_size(data["confidence"], vol_val, data["risk_level"], win_prob=win_prob)

    return {
        "symbol": sym,
        "cached": cached,
        "recommendation": data["recommendation"],
        "confidence": float(data["confidence"]),
        "risk_level": data["risk_level"],
        "weighted_score": float(data.get("weighted_score", 0)),
        "position_sizing": sizing,
        "calibrated_win_prob": win_prob,
        "market_regime": regime,
        "upcoming_event": event_context,
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
        "sentiment_score": float(sentiment_row["score"]) if sentiment_row and sentiment_row["score"] is not None else None,
        "sentiment_history": [
            {"date": str(r["date"]), "score": float(r["score"]), "headline_count": r["headline_count"]}
            for r in hist if r["score"] is not None
        ],
        "sentiment_sources": [
            {"source": r["source"], "score": float(r["score"]), "headline_count": r["headline_count"]}
            for r in source_rows if r["score"] is not None
        ],
        "current_close": data.get("current_close"),
        "days_to_earnings": data.get("days_to_earnings"),
        "bull_case": data.get("bull_case") or "",
        "bear_case": data.get("bear_case") or "",
        "explanation": data.get("explanation") or "",
    }


@router.get("/{symbol}/committee")
@limiter.limit("5/minute")
async def get_committee(
    request: Request,
    sym: str = Depends(validated_symbol),
    force: bool = Query(default=False, description="Re-run even if a committee verdict is stored"),
    conn: asyncpg.Connection = Depends(get_db),
):
    """R10: convene the investment committee on the symbol's latest decision.

    4 specialists (parallel) + Risk Officer; deterministic veto can flip BUY/SELL→HOLD.
    Stored on the decision row — repeat calls reuse it unless force=true.
    """
    decision = await get_latest_decision(conn, sym)
    if not decision:
        raise HTTPException(
            status_code=404,
            detail=f"No decision for {sym} yet — call GET /v1/decision/{sym} first.",
        )

    if not force and decision["committee_json"]:
        cached = decision["committee_json"]
        committee = json.loads(cached) if isinstance(cached, str) else cached
        return {"symbol": sym, "cached": True, **committee}

    signals_json = decision["signals_json"]
    signals = json.loads(signals_json) if isinstance(signals_json, str) else (signals_json or {})

    def _sig_value(name: str) -> float | None:
        v = signals.get(name)
        return v.get("value") if isinstance(v, dict) else None

    fundamentals_row = await get_fundamentals(conn, sym)
    fundamentals = {k: v for k, v in dict(fundamentals_row).items()} if fundamentals_row else None
    regime_row = await get_latest_regime(conn, market_for_symbol(sym))
    regime = regime_row["regime"] if regime_row else None
    price_map = await get_latest_prices(conn, [sym])

    days_to_earnings = None
    try:
        today = datetime.now(tz=timezone.utc).date()
        for er in await get_earnings(conn, sym, limit=5):
            ed = er["earnings_date"]
            if hasattr(ed, "date"):
                ed = ed.date()
            delta = (ed - today).days
            if delta >= 0:
                days_to_earnings = delta
                break
    except Exception:
        pass

    committee = await run_committee(
        symbol=sym,
        recommendation=decision["recommendation"],
        confidence=float(decision["confidence"]),
        signals_json=signals,
        fundamentals=fundamentals,
        regime=regime,
        sentiment_score=_sig_value("sentiment"),
        current_close=price_map.get(sym),
        vol_20=_sig_value("volatility"),
        days_to_earnings=days_to_earnings,
    )
    await set_decision_committee(conn, sym, committee)
    return {"symbol": sym, "cached": False, **committee}


@router.get("/{symbol}/timeframes")
@limiter.limit("20/minute")
async def get_timeframes(
    request: Request,
    sym: str = Depends(validated_symbol),
    intraday: bool = Query(default=False, description="Also fetch 1h intraday from yfinance"),
    conn: asyncpg.Connection = Depends(get_db),
):
    """P8: daily + weekly + monthly (resampled from stored daily) recommendations + confluence.

    intraday=true adds a 1h frame fetched on demand. Long history is needed for the
    coarse frames — monthly stays null until ~2y of daily bars exist.
    """
    now = datetime.now(tz=timezone.utc)
    daily_rows = await get_ohlcv(conn, sym, now - timedelta(days=1095), now)
    if len(daily_rows) < 25:
        raise HTTPException(status_code=422,
                            detail=f"Insufficient daily history for {sym} — run market ingest.")

    sentiment_row = await get_latest_sentiment(conn, sym)
    sentiment_score = float(sentiment_row["score"]) if sentiment_row and sentiment_row["score"] is not None else None

    intraday_rows = None
    if intraday:
        try:
            intraday_rows = await fetch_ohlcv(sym, period="1mo", interval="1h")
        except Exception as exc:
            logger.warning("Intraday fetch failed for %s: %s", sym, exc)

    view = multi_timeframe_view([dict(r) for r in daily_rows], sentiment_score, intraday_rows)
    view["symbol"] = sym
    return view
