"""Scheduled job: refresh the macro event calendar (R8).

Weekly. Pulls the curated upcoming events (`ingest/events.fetch_market_events`) and
upserts them so the decision engine's event-proximity gate sees the latest schedule.
Swap the curated source for a real economic-calendar API here without touching the gate.
"""
import logging
from datetime import datetime, timezone

from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.events import upsert_events
from backend.ingest.events import fetch_market_events
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)


async def _run() -> None:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        job_id = await create_job(conn, "events_run")
        try:
            events = fetch_market_events(datetime.now(tz=timezone.utc).date())
            count = await upsert_events(conn, events)
            await update_job_status(conn, job_id, "completed")
            logger.info("events_run: upserted %d upcoming macro events", count)
        except Exception as exc:
            await update_job_status(conn, job_id, "failed", str(exc))
            raise


async def run() -> None:
    await run_with_retry(_run, "events_run")
