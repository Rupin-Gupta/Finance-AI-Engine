"""FinBERT sentiment scoring → daily aggregate per symbol."""
import asyncio
import logging
from datetime import date
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_LABEL_SCORE = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}


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


async def run_sentiment_for_symbol(symbol: str, headlines: list[str]) -> dict:
    """Return sentiment row dict ready for db upsert."""
    score = await score_headlines_async(headlines)
    return {
        "symbol": symbol,
        "date": date.today(),
        "score": score,
        "headline_count": len(headlines),
        "source": "yahoo_rss",
    }
