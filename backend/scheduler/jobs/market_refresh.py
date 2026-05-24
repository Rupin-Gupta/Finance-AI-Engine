from backend.config import settings
from backend.ingest.pipeline import run_market_ingest
from backend.db.connection import get_db_pool
from backend.scheduler.jobs._base import run_with_retry


async def _run() -> None:
    symbols = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]
    pool = get_db_pool()
    async with pool.acquire() as conn:
        await run_market_ingest(conn, symbols, period="2d")


async def run() -> None:
    await run_with_retry(_run, "market_refresh")
