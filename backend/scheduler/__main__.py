import asyncio
import logging
import signal

from backend.logging_config import configure_logging
from backend.scheduler.worker import start_scheduler, scheduler
from backend.db.connection import init_db_pool, close_db_pool
from backend.db.migrations.migrate import run_migrations
from backend.db.connection import get_db_pool

configure_logging(service="worker")
logger = logging.getLogger(__name__)

_stop_event = asyncio.Event()


def _handle_signal(sig: signal.Signals) -> None:
    logger.info("Received %s — initiating graceful shutdown", sig.name)
    _stop_event.set()


async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal, sig)

    await init_db_pool()
    pool = get_db_pool()
    await run_migrations(pool)
    logger.info("DB migrations complete")

    start_scheduler()
    logger.info("Scheduler started — waiting for stop signal")

    await _stop_event.wait()

    logger.info("Shutting down scheduler (waiting for running jobs)...")
    scheduler.shutdown(wait=True)
    await close_db_pool()
    logger.info("Worker stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())
