"""Fetch financial news headlines from Yahoo Finance RSS per symbol."""
import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import date

import httpx

logger = logging.getLogger(__name__)

_RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
_TIMEOUT = 15


async def fetch_headlines(symbol: str, max_headlines: int = 20) -> list[str]:
    url = _RSS_URL.format(symbol=symbol)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        root = ET.fromstring(resp.text)
        titles = [item.findtext("title", default="") for item in root.iter("item")]
        return [t.strip() for t in titles if t.strip()][:max_headlines]
    except Exception as exc:
        logger.warning("fetch_headlines failed for %s: %s", symbol, exc)
        return []


async def fetch_headlines_batch(symbols: list[str]) -> dict[str, list[str]]:
    results = await asyncio.gather(*[fetch_headlines(s) for s in symbols], return_exceptions=True)
    return {
        sym: (r if isinstance(r, list) else [])
        for sym, r in zip(symbols, results)
    }
