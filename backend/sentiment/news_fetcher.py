"""
Batch RSS fetcher for major financial news sources.
Fetches a small set of feeds once, then maps headlines to symbols by ticker mention.
Avoids per-symbol HTTP calls — O(feeds) not O(symbols).
"""
import asyncio
import logging
import re
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 15
_USER_AGENT = "FinanceAI/1.0 (research bot)"
_MIN_TICKER_LEN = 3  # skip batch matching for 1-2 char tickers (A, F, T)

# Words stripped from company names before keyword matching to avoid false positives
_NAME_STOPWORDS = {
    "inc", "ltd", "corp", "corporation", "industries", "industry",
    "services", "service", "limited", "group", "holdings", "holding",
    "enterprises", "enterprise", "international", "company", "co",
    "plc", "llc", "sa", "ag", "nv", "bv", "the", "bank", "fund",
    "trust", "asset", "management", "capital", "financial", "technologies",
    "technology", "solutions", "systems", "global", "national",
}


def name_keywords(company_name: str) -> list[str]:
    """
    Extract significant tokens from a company name for headline matching.
    Returns up to 2 uppercase tokens, length >= 4, not in stopwords.
    Example: "Infosys Limited"          → ["INFOSYS"]
             "Tata Consultancy Services" → ["TATA", "CONSULTANCY"]
             "Apple Inc"                → ["APPLE"]
    """
    words = re.sub(r"[^\w\s]", "", company_name).split()
    keywords = [
        w.upper() for w in words
        if len(w) >= 4 and w.lower() not in _NAME_STOPWORDS
    ]
    return keywords[:2]


# Global financial news feeds (Reuters, CNBC, MarketWatch)
_GLOBAL_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://feeds.marketwatch.com/marketwatch/marketpulse/",
]

# Indian financial news feeds (MoneyControl, Economic Times, LiveMint)
_INDIA_FEEDS = [
    "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "https://economictimes.indiatimes.com/markets/rss.cms",
    "https://www.livemint.com/rss/markets",
]


def _clean_symbol(symbol: str) -> str:
    return symbol.replace(".NS", "").replace(".BO", "").upper()


def _ticker_in_text(clean_ticker: str, text_upper: str) -> bool:
    """Word-boundary check so 'F' doesn't match inside 'FALL' or 'PROFIT'."""
    if len(clean_ticker) < _MIN_TICKER_LEN:
        return False
    return bool(re.search(r"\b" + re.escape(clean_ticker) + r"\b", text_upper))


def _item_text(item: ET.Element) -> str:
    """Extract title + first 200 chars of description for richer context."""
    title = (item.findtext("title") or "").strip()
    desc = (item.findtext("description") or "").strip()
    # Strip any HTML tags from description
    desc = re.sub(r"<[^>]+>", " ", desc)[:200].strip()
    return f"{title} {desc}".strip()


async def _fetch_feed_items(client: httpx.AsyncClient, url: str) -> list[str]:
    """Fetch one RSS feed; return combined title+description per item."""
    try:
        resp = await client.get(url)
        if resp.status_code == 429:
            logger.warning("Rate-limited: %s", url)
            return []
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        texts = [_item_text(item) for item in root.iter("item")]
        return [t for t in texts if t]
    except Exception as exc:
        logger.warning("Feed fetch failed %s: %s", url, exc)
        return []


def _match_to_symbols(
    all_texts: list[str],
    symbols: list[str],
    name_map: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """
    Map each text to symbols whose clean ticker OR company name keywords appear.
    name_map: {symbol: company_name} — used for Indian stocks where ticker ≠ name in headlines.
    """
    clean_map = {s: _clean_symbol(s) for s in symbols}
    kw_map: dict[str, list[str]] = {}
    if name_map:
        for sym, company_name in name_map.items():
            kws = name_keywords(company_name)
            if kws:
                kw_map[sym] = kws

    result: dict[str, list[str]] = {s: [] for s in symbols}
    for text in all_texts:
        upper_text = text.upper()
        for orig, clean in clean_map.items():
            if _ticker_in_text(clean, upper_text):
                result[orig].append(text)
                continue
            for kw in kw_map.get(orig, []):
                if _ticker_in_text(kw, upper_text):
                    result[orig].append(text)
                    break
    return result


async def _fetch_and_match(
    feeds: list[str],
    symbols: list[str],
    name_map: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=True, headers=headers
    ) as client:
        all_nested = await asyncio.gather(
            *[_fetch_feed_items(client, url) for url in feeds],
            return_exceptions=True,
        )

    all_texts: list[str] = []
    for result in all_nested:
        if isinstance(result, list):
            all_texts.extend(result)

    return _match_to_symbols(all_texts, symbols, name_map)


async def fetch_global_news_batch(
    symbols: list[str], name_map: dict[str, str] | None = None
) -> dict[str, list[str]]:
    """Reuters + CNBC + MarketWatch headlines matched to symbols (+ company names)."""
    return await _fetch_and_match(_GLOBAL_FEEDS, symbols, name_map)


async def fetch_india_news_batch(
    symbols: list[str], name_map: dict[str, str] | None = None
) -> dict[str, list[str]]:
    """MoneyControl + Economic Times + LiveMint headlines matched to symbols (+ company names)."""
    return await _fetch_and_match(_INDIA_FEEDS, symbols, name_map)
