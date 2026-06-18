"""Scheduled job: fetch India market signals (FII/DII, PCR, Gift Nifty) + bulk deals (P5).

Pre-market daily. All fetches are best-effort and graceful — a source outage leaves that
sub-signal NULL (the engine treats it as neutral), it never fails the whole job on a
missing source. The day's row is the shared overlay for all .NS/.BO decisions.
"""
import logging
from datetime import datetime, timezone

from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.india_signals import upsert_market_signals, upsert_bulk_deals
from backend.ingest.india_signals import fetch_india_market_context, fetch_bulk_block_deals
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)


async def _run() -> None:
    pool = get_db_pool()

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "india_signals_run")

    try:
        context = await fetch_india_market_context()
        deals = await fetch_bulk_block_deals()

        async with pool.acquire() as conn:
            await upsert_market_signals(conn, context)
            deal_count = await upsert_bulk_deals(conn, deals)

        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "completed")
        logger.info("india_signals_run: fii=%s dii=%s pcr=%s gift=%s, %d bulk deals (source=%s)",
                    context.get("fii_net_cr"), context.get("dii_net_cr"), context.get("pcr"),
                    context.get("gift_nifty_pct"), deal_count, context.get("source"))
    except Exception as exc:
        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "failed", str(exc))
        raise


async def run() -> None:
    await run_with_retry(_run, "india_signals_run")
