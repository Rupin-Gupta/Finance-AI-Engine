"""Scheduled job: scan tracked symbols for data-quality issues → alerts (P9).

Daily. Flags stale / inconsistent / outlier-laden OHLCV (a `data_quality` alert per
affected symbol, reusing the alerts table) so bad yfinance data is caught before the
engine trades on it. Per-symbol resilient; reconciliation is skipped here (no live
quote fan-out) — the endpoint does live reconcile on demand.
"""
import logging
from datetime import datetime, timedelta, timezone

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.market_data import get_ohlcv
from backend.db.queries.corporate_actions import get_splits
from backend.db.queries.alerts import insert_alert
from backend.analytics.data_quality import assess_data_quality
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 365


async def _run() -> None:
    pool = get_db_pool()
    symbols = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=_LOOKBACK_DAYS)

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "data_quality_run")

    flagged = 0
    try:
        for sym in symbols:
            try:
                async with pool.acquire() as conn:
                    rows = [dict(r) for r in await get_ohlcv(conn, sym, start, now)]
                    if not rows:
                        continue
                    split_dates = {str(d) for d, _ in await get_splits(conn, sym)}
                    report = assess_data_quality(rows, split_dates=split_dates, now=now)
                    if not report["ok"]:
                        await insert_alert(conn, sym, "data_quality",
                                           float(len(report["issues"])), 0.0)
                        flagged += 1
            except Exception as exc:
                logger.warning("data_quality_run: %s failed: %s", sym, exc)

        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "completed")
        logger.info("data_quality_run: flagged %d/%d symbols", flagged, len(symbols))
    except Exception as exc:
        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "failed", str(exc))
        raise


async def run() -> None:
    await run_with_retry(_run, "data_quality_run")
