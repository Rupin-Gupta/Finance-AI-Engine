import asyncio
import logging
from abc import ABC, abstractmethod

from backend.config import settings

logger = logging.getLogger(__name__)

_LLM_TIMEOUT = 30.0
_MAX_RETRIES = 3
_RETRY_STATUSES = {429, 500, 502, 503, 504}


async def _with_retry(fn, label: str) -> str:
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return await asyncio.wait_for(fn(), timeout=_LLM_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("%s timed out (attempt %d/%d)", label, attempt, _MAX_RETRIES)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                wait = 2 ** (attempt - 1)
                logger.warning("%s error %s (attempt %d/%d) — retrying in %ds",
                               label, status, attempt, _MAX_RETRIES, wait)
                await asyncio.sleep(wait)
                continue
            raise
        if attempt < _MAX_RETRIES:
            await asyncio.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"{label} failed after {_MAX_RETRIES} attempts")


class LLMClient(ABC):
    @abstractmethod
    async def complete(self, prompt: str) -> str: ...


class OpenAIClient(LLMClient):
    async def complete(self, prompt: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=_LLM_TIMEOUT, max_retries=0)

        async def _call() -> str:
            resp = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content

        return await _with_retry(_call, f"OpenAI/{settings.llm_model}")


class GeminiClient(LLMClient):
    async def complete(self, prompt: str) -> str:
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.llm_model)

        async def _call() -> str:
            resp = await model.generate_content_async(prompt)
            return resp.text

        return await _with_retry(_call, f"Gemini/{settings.llm_model}")


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "gemini":
        return GeminiClient()
    return OpenAIClient()
