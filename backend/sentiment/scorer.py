"""FinBERT sentiment scoring → daily aggregate per symbol."""
import asyncio
import logging
from datetime import date
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_LABEL_SCORE = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
_STOCKTWITS_LABEL_SCORE = {"Bullish": 1.0, "Bearish": -1.0}


@lru_cache(maxsize=1)
def _load_pipeline() -> Any:
    from transformers import pipeline as hf_pipeline
    return hf_pipeline(
        "text-classification",
        model="ProsusAI/finbert",
        tokenizer="ProsusAI/finbert",
        device=-1,
        top_k=None,
    )


def _score_headline(pipe: Any, text: str) -> float:
    """Return net sentiment score in [-1, 1] for a single headline."""
    try:
        results = pipe(text[:512], truncation=True)
        # results is list of list[{label, score}]
        preds = results[0] if isinstance(results[0], list) else results
        best = max(preds, key=lambda x: x["score"])
        return _LABEL_SCORE.get(best["label"].lower(), 0.0)
    except Exception:
        return 0.0


_MAX_HEADLINES = 100


def score_headlines(headlines: list[str]) -> float:
    """Return daily aggregate sentiment score in [-1, 1]."""
    if not headlines:
        return 0.0
    capped = headlines[:_MAX_HEADLINES]
    if len(headlines) > _MAX_HEADLINES:
        logger.warning("score_headlines: capped %d headlines to %d", len(headlines), _MAX_HEADLINES)
    pipe = _load_pipeline()
    scores = [_score_headline(pipe, h) for h in capped]
    return round(sum(scores) / len(scores), 4)


async def score_headlines_async(headlines: list[str]) -> float:
    return await asyncio.to_thread(score_headlines, headlines)


def score_stocktwits(messages: list[tuple[str, str | None]]) -> float:
    """
    Score StockTwits messages using native Bullish/Bearish labels where available,
    falling back to FinBERT for unlabelled messages.
    """
    if not messages:
        return 0.0
    pipe = _load_pipeline()
    scores = []
    for body, label in messages:
        if label in _STOCKTWITS_LABEL_SCORE:
            scores.append(_STOCKTWITS_LABEL_SCORE[label])
        else:
            scores.append(_score_headline(pipe, body))
    return round(sum(scores) / len(scores), 4)


async def score_stocktwits_async(messages: list[tuple[str, str | None]]) -> float:
    return await asyncio.to_thread(score_stocktwits, messages)


async def run_sentiment_for_symbol(symbol: str, headlines: list[str]) -> dict:
    """Return yahoo_finance sentiment row dict ready for db upsert."""
    score = await score_headlines_async(headlines)
    return {
        "symbol": symbol,
        "date": date.today(),
        "score": score,
        "headline_count": len(headlines),
        "source": "yahoo_finance",
    }


def _deduplicate_across_sources(
    text_sources: dict[str, list[str]]
) -> dict[str, list[str]]:
    """
    Remove exact-duplicate texts that appear in multiple sources.
    First source wins; later sources drop already-seen texts.
    Prevents the same Reuters headline on Yahoo + Google News + global_news
    from being scored three times.
    """
    seen: set[str] = set()
    deduped: dict[str, list[str]] = {}
    for source, texts in text_sources.items():
        unique = []
        for t in texts:
            norm = t.strip().lower()
            if norm not in seen:
                seen.add(norm)
                unique.append(t)
        deduped[source] = unique
    return deduped


async def run_social_sentiment_for_symbol(
    symbol: str,
    text_sources: dict[str, list[str]],
    stocktwits_messages: list[tuple[str, str | None]],
) -> list[dict]:
    """
    Score all sources for one symbol concurrently.

    text_sources: {source_name: [headline/post strings]} for any FinBERT-scored source.
    stocktwits_messages: [(body, label)] — uses native Bullish/Bearish labels first.
    Returns list of per-source rows ready for upsert (skips empty sources).
    """
    today = date.today()
    text_sources = _deduplicate_across_sources(text_sources)

    async def _score_text(texts: list[str], source: str) -> dict | None:
        if not texts:
            return None
        score = await score_headlines_async(texts)
        return {"symbol": symbol, "date": today, "score": score,
                "headline_count": len(texts), "source": source}

    async def _score_stocktwits() -> dict | None:
        if not stocktwits_messages:
            return None
        score = await score_stocktwits_async(stocktwits_messages)
        return {"symbol": symbol, "date": today, "score": score,
                "headline_count": len(stocktwits_messages), "source": "stocktwits"}

    tasks = [_score_text(texts, src) for src, texts in text_sources.items()]
    tasks.append(_score_stocktwits())

    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]
