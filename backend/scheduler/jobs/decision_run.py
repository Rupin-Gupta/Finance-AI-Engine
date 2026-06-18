"""Scheduled job: pull signals → forecast → engine → upsert decisions."""
import logging
from datetime import datetime, timedelta, timezone

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.analytics import get_analytics
from backend.db.queries.market_data import get_ohlcv
from backend.db.queries.sentiment import get_latest_sentiment
from backend.db.queries.decisions import upsert_decision, upsert_forecasts
from backend.db.queries.fundamentals import get_earnings
from backend.db.queries.signal_weights import get_active_weights
from backend.db.queries.india_signals import get_latest_market_signals, market_context
from backend.db.queries.regime import get_latest_regime
from backend.db.queries.events import get_upcoming_events
from backend.analytics.regime import market_for_symbol, regime_adjusted_weights
from backend.analytics.events import nearest_gating_event
from backend.ml.inference import predict_symbol_prob
from backend.decision.signals import compute_all_signals, SIGNAL_WEIGHTS
from backend.decision.engine import make_recommendation
from backend.decision.forecast import run_forecast
from backend.llm.client import get_llm_client
from backend.llm.prompts import build_decision_prompt
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)


async def _process_symbol(conn, sym: str, india_context: dict | None = None,
                          weights: dict | None = None,
                          regimes: dict[str, str | None] | None = None,
                          events: list[dict] | None = None) -> None:
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=90)

    analytics_rows = await get_analytics(conn, sym, start, now)
    latest = analytics_rows[-1] if analytics_rows else None

    close = rsi = sma_20 = momentum_10 = vol_20 = ema_9 = ema_20 = None
    if latest:
        rsi = float(latest["rsi_14"]) if latest["rsi_14"] is not None else None
        sma_20 = float(latest["sma_20"]) if latest["sma_20"] is not None else None
        momentum_10 = float(latest["momentum_10"]) if latest["momentum_10"] is not None else None
        vol_20 = float(latest["volatility_20"]) if latest["volatility_20"] is not None else None
        ema_9 = float(latest["ema_9"]) if latest["ema_9"] is not None else None
        ema_20 = float(latest["ema_20"]) if latest["ema_20"] is not None else None

    ohlcv_rows = await get_ohlcv(conn, sym, start, now)
    volume_ratio = None
    if ohlcv_rows:
        close = float(ohlcv_rows[-1]["close"])
        vols = [float(r["volume"]) for r in ohlcv_rows if r["volume"] is not None]
        if len(vols) >= 20:
            avg_vol = sum(vols[-20:]) / 20
            if avg_vol > 0:
                volume_ratio = vols[-1] / avg_vol
        raw = [{"timestamp": r["timestamp"], "close": float(r["close"])} for r in ohlcv_rows]
        forecast_rows = await run_forecast(sym, raw, horizon_days=7)
        if forecast_rows:
            await upsert_forecasts(conn, forecast_rows)
    else:
        forecast_rows = []

    predicted_close = float(forecast_rows[0]["predicted_close"]) if forecast_rows else None

    sentiment_row = await get_latest_sentiment(conn, sym)
    sentiment_score = float(sentiment_row["score"]) if sentiment_row and sentiment_row["score"] is not None else None

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

    region = market_for_symbol(sym)
    ctx = india_context if (sym.endswith(".NS") or sym.endswith(".BO")) else None
    regime = (regimes or {}).get(region)
    sym_weights = regime_adjusted_weights(weights or SIGNAL_WEIGHTS, regime) if regime else weights
    event_ctx = nearest_gating_event(events or [], now.date(), region)
    ml_prob = await predict_symbol_prob(conn, latest, close, sentiment_score)
    signals = compute_all_signals(close, rsi, sma_20, momentum_10, vol_20, sentiment_score,
                                  predicted_close, ema_9=ema_9, ema_20=ema_20,
                                  volume_ratio=volume_ratio, weights=sym_weights,
                                  india_context=ctx, ml_prob=ml_prob)
    result = make_recommendation(signals, vol_20, days_to_earnings=days_to_earnings,
                                 regime=regime, event_context=event_ctx)

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

    await upsert_decision(conn, {
        "symbol": sym,
        "recommendation": result["recommendation"],
        "confidence": result["confidence"],
        "signals_json": result["signals_json"],
        "risk_level": result["risk_level"],
        "explanation": explanation,
    })


async def _run() -> None:
    pool = get_db_pool()
    symbols = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "decision_run")
        # Load the day's India market overlay once; reused for all .NS/.BO symbols.
        india_context = market_context(await get_latest_market_signals(conn))
        # Auto-tuned weights (None → engine falls back to default SIGNAL_WEIGHTS).
        weights = await get_active_weights(conn)
        # R5: the day's market regime per market (None → no tilt, no cap).
        regimes: dict[str, str | None] = {}
        for market in ("US", "INDIA"):
            row = await get_latest_regime(conn, market)
            regimes[market] = row["regime"] if row else None
        # R8: upcoming macro events once; nearest gating event picked per symbol's market.
        events = [dict(r) for r in await get_upcoming_events(conn, days=14)]

    failed: list[str] = []
    for sym in symbols:
        try:
            async with pool.acquire() as conn:
                await _process_symbol(conn, sym, india_context=india_context, weights=weights,
                                      regimes=regimes, events=events)
        except Exception as exc:
            logger.error("decision_run: failed for %s: %s", sym, exc, exc_info=True)
            failed.append(sym)

    async with pool.acquire() as conn:
        if failed:
            await update_job_status(conn, job_id, "failed", f"Failed symbols: {failed}")
        else:
            await update_job_status(conn, job_id, "completed")

    logger.info("decision_run: processed %d/%d symbols", len(symbols) - len(failed), len(symbols))
    if failed:
        raise RuntimeError(f"decision_run failed for symbols: {failed}")


async def run() -> None:
    await run_with_retry(_run, "decision_run")
