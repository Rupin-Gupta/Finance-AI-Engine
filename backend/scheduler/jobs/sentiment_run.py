"""Scheduled job: fetch headlines → FinBERT score → upsert sentiment."""
import logging

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.sentiment import upsert_sentiment
from backend.sentiment.fetcher import fetch_headlines_batch
from backend.sentiment.scorer import run_sentiment_for_symbol
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)


async def _run() -> None:
    pool = get_db_pool()
    symbols = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "sentiment_run")
    try:
        headlines_map = await fetch_headlines_batch(symbols)
        rows = []
        for sym, headlines in headlines_map.items():
            row = await run_sentiment_for_symbol(sym, headlines)
            rows.append(row)

        if rows:
            async with pool.acquire() as conn:
                await upsert_sentiment(conn, rows)

        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "completed")
        logger.info("sentiment_run: scored %d symbols", len(rows))
    except Exception as exc:
        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "failed", str(exc))
        raise


async def run() -> None:
    await run_with_retry(_run, "sentiment_run")
