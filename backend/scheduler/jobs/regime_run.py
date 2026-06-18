"""Scheduled job: classify the daily market regime per market (R5).

Pre-market daily, before decision_run, so the day's decisions pick up the fresh
regime. Per-market resilient: one market's data outage never blocks the other.
Index + VIX history comes from yfinance (not the tracked-symbol ingest); breadth
comes from stored market_data.
"""
import logging
from datetime import datetime, timezone

from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.market_data import get_market_breadth
from backend.db.queries.regime import upsert_regime
from backend.ingest.market import fetch_ohlcv
from backend.analytics.regime import (
    MARKET_INDEXES, classify_regime, compute_regime_features,
)
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)


async def _classify_market(conn, market: str) -> dict:
    cfg = MARKET_INDEXES[market]

    index_rows = await fetch_ohlcv(cfg["index"], period="1y", interval="1d")
    features = compute_regime_features([r["close"] for r in index_rows])

    vix = None
    try:
        vix_rows = await fetch_ohlcv(cfg["vix"], period="5d", interval="1d")
        if vix_rows:
            vix = float(vix_rows[-1]["close"])
    except Exception as exc:
        logger.warning("regime_run: %s VIX fetch failed: %s", market, exc)

    breadth = await get_market_breadth(conn, market)

    verdict = classify_regime(
        features["index_close"], features["sma_50"], features["sma_200"],
        vix=vix, realized_vol=features["realized_vol"], breadth_pct=breadth,
    )
    return {
        "date": datetime.now(tz=timezone.utc).date(),
        "market": market,
        "regime": verdict["regime"],
        "reason": verdict["reason"],
        "index_symbol": cfg["index"],
        "index_close": features["index_close"],
        "sma_50": features["sma_50"],
        "sma_200": features["sma_200"],
        "vix": vix,
        "realized_vol": features["realized_vol"],
        "breadth_pct": breadth,
    }


async def _run() -> None:
    pool = get_db_pool()

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "regime_run")

    failed: list[str] = []
    for market in MARKET_INDEXES:
        try:
            async with pool.acquire() as conn:
                row = await _classify_market(conn, market)
                await upsert_regime(conn, row)
            logger.info("regime_run: %s → %s (%s)", market, row["regime"], row["reason"])
        except Exception as exc:
            logger.error("regime_run: failed for %s: %s", market, exc, exc_info=True)
            failed.append(market)

    async with pool.acquire() as conn:
        if failed:
            await update_job_status(conn, job_id, "failed", f"Failed markets: {failed}")
        else:
            await update_job_status(conn, job_id, "completed")

    if failed:
        raise RuntimeError(f"regime_run failed for markets: {failed}")


async def run() -> None:
    await run_with_retry(_run, "regime_run")
