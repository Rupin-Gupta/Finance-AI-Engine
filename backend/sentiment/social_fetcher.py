"""Fetch social sentiment data from Reddit, StockTwits, and Google News RSS."""
import asyncio
import logging
import re
import xml.etree.ElementTree as ET

import httpx

from backend.sentiment.news_fetcher import name_keywords

logger = logging.getLogger(__name__)

_TIMEOUT = 15
_USER_AGENT = "FinanceAI/1.0 (research bot)"
_REDDIT_SUBREDDITS = ["wallstreetbets", "stocks", "investing"]


_MIN_TICKER_LEN = 3  # skip batch matching for 1-2 char tickers (A, F, T) — too ambiguous


def _clean_symbol(symbol: str) -> str:
    """Strip exchange suffix for external search queries."""
    return symbol.replace(".NS", "").replace(".BO", "")


def _ticker_in_text(clean_ticker: str, text_upper: str) -> bool:
    """Word-boundary check: 'F' must appear as isolated token, not inside 'FAIL'."""
    if len(clean_ticker) < _MIN_TICKER_LEN:
        return False
    return bool(re.search(r"\b" + re.escape(clean_ticker) + r"\b", text_upper))


# ---------------------------------------------------------------------------
# Reddit  (public JSON API — no credentials required)
# ---------------------------------------------------------------------------

async def fetch_reddit_batch(
    symbols: list[str],
    name_map: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """
    Fetch recent posts from WSB/stocks/investing, map mentions back to symbols.
    Matches by ticker AND company name keywords (for Indian stocks).
    3 subreddit requests total regardless of symbol count.
    """
    clean_map = {s: _clean_symbol(s).upper() for s in symbols}
    kw_map: dict[str, list[str]] = {}
    if name_map:
        for sym, company_name in name_map.items():
            kws = name_keywords(company_name)
            if kws:
                kw_map[sym] = kws

    posts_by_symbol: dict[str, list[str]] = {s: [] for s in symbols}

    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers, follow_redirects=True) as client:
        for sub in _REDDIT_SUBREDDITS:
            url = f"https://www.reddit.com/r/{sub}/new.json?limit=100"
            try:
                resp = await client.get(url)
                if resp.status_code == 429:
                    logger.warning("Reddit rate-limited on r/%s", sub)
                    continue
                resp.raise_for_status()
                children = resp.json().get("data", {}).get("children", [])
                for child in children:
                    data = child.get("data", {})
                    title = data.get("title", "")
                    body = data.get("selftext", "")[:300]
                    combined = f"{title} {body}".upper()
                    for orig_sym in symbols:
                        clean = clean_map[orig_sym]
                        matched = _ticker_in_text(clean, combined)
                        if not matched:
                            matched = any(
                                _ticker_in_text(kw, combined)
                                for kw in kw_map.get(orig_sym, [])
                            )
                        if matched:
                            posts_by_symbol[orig_sym].append(title)
                            if body and body not in ("[deleted]", "[removed]"):
                                posts_by_symbol[orig_sym].append(body)
            except Exception as exc:
                logger.warning("Reddit fetch failed for r/%s: %s", sub, exc)

    return posts_by_symbol


# ---------------------------------------------------------------------------
# StockTwits  (public API — returns native Bullish/Bearish labels)
# ---------------------------------------------------------------------------

async def fetch_stocktwits(
    symbol: str, max_messages: int = 30
) -> list[tuple[str, str | None]]:
    """
    Returns list of (message_body, sentiment_label).
    sentiment_label is 'Bullish', 'Bearish', or None.
    """
    clean = _clean_symbol(symbol)
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{clean}.json"
    headers = {"User-Agent": _USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code in (404, 422, 429):
                logger.warning("StockTwits %s for %s", resp.status_code, symbol)
                return []
            resp.raise_for_status()
            messages = resp.json().get("messages", [])
            result = []
            for msg in messages[:max_messages]:
                body = msg.get("body", "")
                entities = msg.get("entities", {})
                sentiment_entity = entities.get("sentiment")
                label = sentiment_entity.get("basic") if sentiment_entity else None
                if body:
                    result.append((body, label))
            return result
    except Exception as exc:
        logger.warning("StockTwits fetch failed for %s: %s", symbol, exc)
        return []


async def fetch_stocktwits_batch(
    symbols: list[str], concurrency: int = 8
) -> dict[str, list[tuple[str, str | None]]]:
    sem = asyncio.Semaphore(concurrency)

    async def _fetch(sym: str) -> tuple[str, list]:
        async with sem:
            return sym, await fetch_stocktwits(sym)

    results = await asyncio.gather(*[_fetch(s) for s in symbols], return_exceptions=True)
    return {
        sym: msgs
        for r in results
        if isinstance(r, tuple)
        for sym, msgs in [r]
    }


# ---------------------------------------------------------------------------
# Google News RSS  (no auth — global coverage)
# ---------------------------------------------------------------------------

def _item_text(item: ET.Element) -> str:
    """Title + first 200 chars of description for richer FinBERT context."""
    title = (item.findtext("title") or "").strip()
    desc = (item.findtext("description") or "").strip()
    desc = re.sub(r"<[^>]+>", " ", desc)[:200].strip()
    return f"{title} {desc}".strip()


async def fetch_google_news(symbol: str, max_articles: int = 30) -> list[str]:
    clean = _clean_symbol(symbol)
    url = (
        f"https://news.google.com/rss/search"
        f"?q={clean}+stock&hl=en-US&gl=US&ceid=US:en"
    )
    headers = {"User-Agent": _USER_AGENT}
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, follow_redirects=True, headers=headers
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        root = ET.fromstring(resp.text)
        texts = [_item_text(item) for item in root.iter("item")]
        return [t for t in texts if t][:max_articles]
    except Exception as exc:
        logger.warning("Google News fetch failed for %s: %s", symbol, exc)
        return []


async def fetch_google_news_batch(
    symbols: list[str], concurrency: int = 8
) -> dict[str, list[str]]:
    sem = asyncio.Semaphore(concurrency)

    async def _fetch(sym: str) -> tuple[str, list]:
        async with sem:
            return sym, await fetch_google_news(sym)

    results = await asyncio.gather(*[_fetch(s) for s in symbols], return_exceptions=True)
    return {
        sym: headlines
        for r in results
        if isinstance(r, tuple)
        for sym, headlines in [r]
    }
