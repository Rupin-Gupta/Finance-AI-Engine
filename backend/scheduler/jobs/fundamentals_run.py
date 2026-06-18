"""Scheduled job: refresh fundamental data and earnings calendar for tracked symbols."""
import logging

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.stocks import ensure_stocks, update_stock_names, update_stock_sectors
from backend.db.queries.fundamentals import upsert_fundamentals, upsert_earnings
from backend.analytics.fundamentals import fetch_fundamentals, fetch_earnings
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)


async def _process_symbol(conn, sym: str) -> None:
    await ensure_stocks(conn, [sym])
    fund_data = await fetch_fundamentals(sym)
    await upsert_fundamentals(conn, fund_data)
    if fund_data.get("name"):
        await update_stock_names(conn, {sym: fund_data["name"]})
    if fund_data.get("sector"):
        await update_stock_sectors(conn, {sym: fund_data["sector"]})
    earnings_data = await fetch_earnings(sym)
    if earnings_data:
        await upsert_earnings(conn, earnings_data)
    logger.info("fundamentals_run: refreshed %s", sym)


async def _run() -> None:
    pool = get_db_pool()
    symbols = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "fundamentals_run")

    failed: list[str] = []
    for sym in symbols:
        try:
            async with pool.acquire() as conn:
                await _process_symbol(conn, sym)
        except Exception as exc:
            logger.error("fundamentals_run: failed for %s: %s", sym, exc, exc_info=True)
            failed.append(sym)

    async with pool.acquire() as conn:
        if failed:
            await update_job_status(conn, job_id, "failed", f"Failed symbols: {failed}")
        else:
            await update_job_status(conn, job_id, "completed")

    logger.info("fundamentals_run: processed %d/%d symbols", len(symbols) - len(failed), len(symbols))
    if failed:
        raise RuntimeError(f"fundamentals_run failed for symbols: {failed}")


async def run() -> None:
    await run_with_retry(_run, "fundamentals_run")
