"""Scheduled job: fetch splits/dividends for tracked symbols → corporate_actions table."""
import logging

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.stocks import ensure_stocks
from backend.db.queries.corporate_actions import upsert_corporate_actions
from backend.analytics.corporate_actions import fetch_corporate_actions
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)


async def _process_symbol(conn, sym: str) -> None:
    await ensure_stocks(conn, [sym])
    actions = await fetch_corporate_actions(sym)
    count = await upsert_corporate_actions(conn, sym, actions)
    logger.info("corporate_actions_run: %s — %d actions", sym, count)


async def _run() -> None:
    pool = get_db_pool()
    symbols = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "corporate_actions_run")

    failed: list[str] = []
    for sym in symbols:
        try:
            async with pool.acquire() as conn:
                await _process_symbol(conn, sym)
        except Exception as exc:
            logger.error("corporate_actions_run: failed for %s: %s", sym, exc)
            failed.append(sym)

    async with pool.acquire() as conn:
        if failed:
            await update_job_status(conn, job_id, "failed", f"Failed symbols: {failed}")
        else:
            await update_job_status(conn, job_id, "completed")

    logger.info("corporate_actions_run: processed %d/%d symbols",
                len(symbols) - len(failed), len(symbols))
    if failed:
        raise RuntimeError(f"corporate_actions_run failed for symbols: {failed}")


async def run() -> None:
    await run_with_retry(_run, "corporate_actions_run")
