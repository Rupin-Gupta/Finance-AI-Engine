import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 30
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_RETRIES = 3


async def fetch_document_text(source_url: str) -> str:
    """Fetch raw text from URL with retry and size cap. Raises on permanent failure."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(source_url)
                resp.raise_for_status()
                if len(resp.content) > _MAX_BYTES:
                    raise ValueError(
                        f"Document at {source_url} exceeds {_MAX_BYTES // (1024*1024)} MB limit"
                    )
                return resp.text
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt - 1)
                logger.warning("fetch_document_text attempt %d/%d failed (%s) — retrying in %ds",
                               attempt, _MAX_RETRIES, exc, wait)
                await asyncio.sleep(wait)
        except Exception as exc:
            raise
    raise RuntimeError(f"fetch_document_text failed after {_MAX_RETRIES} attempts: {last_exc}")
