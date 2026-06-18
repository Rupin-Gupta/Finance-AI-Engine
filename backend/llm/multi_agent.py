"""Bull / Bear / Synthesis multi-agent decision explanation.

Flow:
  1. Bull agent + Bear agent run in parallel (asyncio.gather).
  2. Synthesis agent receives both outputs and renders a balanced verdict.

All three use the shared LLMClient with its existing timeout + retry logic.
"""
import asyncio
import logging

from backend.llm.client import get_llm_client
from backend.llm.prompts import build_bull_prompt, build_bear_prompt, build_synthesis_prompt

logger = logging.getLogger(__name__)


async def _safe_complete(label: str, prompt: str) -> str:
    try:
        return await get_llm_client().complete(prompt)
    except Exception as exc:
        logger.warning("Multi-agent %s failed: %s", label, exc)
        return ""


async def run_bull_bear_synthesis(
    symbol: str,
    recommendation: str,
    confidence: float,
    risk_level: str,
    signals_json: dict,
    sentiment_score: float | None,
    predicted_close: float | None,
    current_close: float | None,
    days_to_earnings: int | None = None,
) -> dict[str, str]:
    """
    Run Bull + Bear agents concurrently, then Synthesis.
    Returns {"bull": str, "bear": str, "synthesis": str}.
    On partial failure the failed field is an empty string.
    """
    bull_prompt = build_bull_prompt(
        symbol, recommendation, confidence, risk_level, signals_json,
        sentiment_score, predicted_close, current_close,
    )
    bear_prompt = build_bear_prompt(
        symbol, recommendation, confidence, risk_level, signals_json,
        sentiment_score, predicted_close, current_close,
    )

    bull_case, bear_case = await asyncio.gather(
        _safe_complete("bull", bull_prompt),
        _safe_complete("bear", bear_prompt),
    )

    synthesis_prompt = build_synthesis_prompt(
        symbol, recommendation, confidence, risk_level,
        bull_case, bear_case, days_to_earnings,
    )
    synthesis = await _safe_complete("synthesis", synthesis_prompt)

    return {"bull": bull_case, "bear": bear_case, "synthesis": synthesis}
