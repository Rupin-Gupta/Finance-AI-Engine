"""Scheduled job: fetch headlines from all sources → FinBERT score → upsert sentiment."""
import asyncio
import logging

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.sentiment import upsert_sentiment
from backend.db.queries.stocks import get_symbol_names
from backend.sentiment.fetcher import fetch_headlines_batch
from backend.sentiment.social_fetcher import (
    fetch_reddit_batch,
    fetch_stocktwits_batch,
    fetch_google_news_batch,
)
from backend.sentiment.news_fetcher import fetch_global_news_batch, fetch_india_news_batch
from backend.sentiment.scorer import run_social_sentiment_for_symbol
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)


async def _run() -> None:
    pool = get_db_pool()
    symbols = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "sentiment_run")
        name_map = await get_symbol_names(conn, symbols)

    logger.info(
        "sentiment_run: %d symbols, %d with company names loaded",
        len(symbols), len(name_map),
    )

    try:
        logger.info("sentiment_run: fetching %d symbols from 6 sources", len(symbols))

        # All source fetches run concurrently; batch fetchers receive name_map
        # so Indian stocks are matched by company name in news headlines too
        (
            yahoo_map,
            reddit_map,
            stocktwits_map,
            google_map,
            global_map,
            india_map,
        ) = await asyncio.gather(
            fetch_headlines_batch(symbols),
            fetch_reddit_batch(symbols, name_map=name_map),
            fetch_stocktwits_batch(symbols),
            fetch_google_news_batch(symbols),
            fetch_global_news_batch(symbols, name_map=name_map),
            fetch_india_news_batch(symbols, name_map=name_map),
        )

        rows: list[dict] = []
        failed: list[str] = []

        for sym in symbols:
            try:
                text_sources = {
                    "yahoo_finance": yahoo_map.get(sym, []),
                    "reddit":        reddit_map.get(sym, []),
                    "google_news":   google_map.get(sym, []),
                    "global_news":   global_map.get(sym, []),
                    "india_news":    india_map.get(sym, []),
                }
                source_rows = await run_social_sentiment_for_symbol(
                    symbol=sym,
                    text_sources=text_sources,
                    stocktwits_messages=stocktwits_map.get(sym, []),
                )
                rows.extend(source_rows)
            except Exception as exc:
                logger.warning("sentiment_run: scoring failed for %s: %s", sym, exc)
                failed.append(sym)

        if rows:
            async with pool.acquire() as conn:
                count = await upsert_sentiment(conn, rows)
            logger.info(
                "sentiment_run: upserted %d source rows for %d symbols",
                count, len(symbols),
            )

        status = "failed" if failed else "completed"
        error = f"failed symbols: {failed}" if failed else None
        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, status, error)

        logger.info("sentiment_run: done — %d rows, %d failed symbols", len(rows), len(failed))

    except Exception as exc:
        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "failed", str(exc))
        raise


async def run() -> None:
    await run_with_retry(_run, "sentiment_run")
