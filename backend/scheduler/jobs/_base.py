"""Job retry wrapper with exponential backoff."""
import asyncio
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


async def run_with_retry(
    fn: Callable[[], Awaitable[None]],
    job_name: str,
    max_attempts: int = 3,
    base_backoff: float = 60.0,
) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            await fn()
            return
        except Exception as exc:
            if attempt == max_attempts:
                logger.error("%s failed after %d attempts: %s", job_name, max_attempts, exc, exc_info=True)
                raise
            wait = base_backoff * (2 ** (attempt - 1))
            logger.warning("%s attempt %d/%d failed: %s — retrying in %.0fs",
                           job_name, attempt, max_attempts, exc, wait)
            await asyncio.sleep(wait)
