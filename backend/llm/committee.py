"""R10: multi-agent investment committee — 4 specialists in parallel + Risk Officer.

Extends the Bull/Bear/Synthesis pattern (multi_agent.py): Technical, Fundamental,
Macro, and Sentiment specialists each see only their domain slice (context isolation),
run concurrently via asyncio.gather, then the Risk Officer reads all four distilled
views plus hard risk facts and renders a narrative.

The VETO itself is deterministic code, not LLM output — LLM consensus is sycophantic
and must never be the safety mechanism. `risk_officer_gate` flips a non-HOLD call to
HOLD when market-level risk facts say conviction is unwarranted.
"""
import asyncio
import logging
import re

from backend.llm.client import get_llm_client
from backend.llm.prompts import build_specialist_prompt, build_risk_officer_prompt

logger = logging.getLogger(__name__)

SPECIALIST_ROLES = ("technical", "fundamental", "macro", "sentiment")

_EXTREME_VOL = 0.55          # mirrors engine._EXTREME_VOL_THRESHOLD
_EARNINGS_VETO_DAYS = 3      # binary event imminent — no fresh conviction trades

# Tolerate markdown/punctuation the LLM sometimes injects: "**VOTE:** HOLD",
# "VOTE - HOLD", "VOTE→ BUY". Plain `VOTE:\s*(...)` missed these → blank vote.
_VOTE_RE = re.compile(r"VOTE\b[\s:*_\-–—>]*(BUY|SELL|HOLD)", re.IGNORECASE)
_VERDICT_RE = re.compile(r"\b(BUY|SELL|HOLD)\b", re.IGNORECASE)


def parse_vote(text: str) -> str | None:
    t = text or ""
    m = _VOTE_RE.search(t)
    if m:
        return m.group(1).upper()
    # Fallback: the agent answered but mangled the VOTE line — take its last
    # standalone verdict word (the conclusion) rather than rendering a blank "—".
    # Empty/failed responses still yield None (honest "agent unavailable").
    hits = _VERDICT_RE.findall(t)
    return hits[-1].upper() if hits else None


def risk_officer_gate(
    recommendation: str,
    vol_20: float | None,
    regime: str | None,
    days_to_earnings: int | None,
) -> dict:
    """Deterministic veto: BUY/SELL flips to HOLD when hard risk facts demand it."""
    reasons: list[str] = []
    if recommendation == "HOLD":
        return {"vetoed": False, "reasons": reasons}
    if vol_20 is not None and vol_20 > _EXTREME_VOL:
        reasons.append(f"20-day volatility {vol_20:.2f} above extreme threshold {_EXTREME_VOL}")
    if regime == "high_vol":
        reasons.append("market regime is high-volatility")
    if days_to_earnings is not None and days_to_earnings <= _EARNINGS_VETO_DAYS:
        reasons.append(f"earnings in {days_to_earnings} day(s) — binary event risk")
    return {"vetoed": bool(reasons), "reasons": reasons}


async def _safe_complete(label: str, prompt: str) -> str:
    try:
        return await get_llm_client().complete(prompt)
    except Exception as exc:
        logger.warning("Committee %s agent failed: %s", label, exc)
        return ""


def _specialist_context(role: str, fundamentals: dict | None, regime: str | None,
                        sentiment_score: float | None, current_close: float | None,
                        vol_20: float | None) -> str:
    """Domain slice per specialist — context isolation, not the full firehose."""
    if role == "technical":
        price = f"${current_close:.2f}" if current_close is not None else "N/A"
        return f"CURRENT PRICE: {price}"
    if role == "fundamental":
        f = fundamentals or {}
        lines = [f"- {k}: {f[k]}" for k in
                 ("pe_trailing", "pe_forward", "eps_trailing", "profit_margins",
                  "analyst_target", "analyst_rating", "market_cap")
                 if f.get(k) is not None]
        return "FUNDAMENTALS:\n" + ("\n".join(lines) if lines else "- no stored fundamentals")
    if role == "macro":
        vol = f"{vol_20:.2f}" if vol_20 is not None else "N/A"
        return f"MARKET REGIME: {regime or 'unknown'}\n20-DAY ANNUALIZED VOL: {vol}"
    sent = f"{sentiment_score:.3f}" if sentiment_score is not None else "N/A"
    return f"AGGREGATE SENTIMENT SCORE: {sent} (range -1 to +1, 6 sources, count-weighted)"


async def run_committee(
    symbol: str,
    recommendation: str,
    confidence: float,
    signals_json: dict,
    fundamentals: dict | None = None,
    regime: str | None = None,
    sentiment_score: float | None = None,
    current_close: float | None = None,
    vol_20: float | None = None,
    days_to_earnings: int | None = None,
) -> dict:
    """Run the committee. Returns views, votes, risk-officer narrative, and the
    (possibly vetoed) final recommendation. Any failed agent degrades to ""."""
    prompts = {
        role: build_specialist_prompt(
            role, symbol, recommendation, signals_json,
            _specialist_context(role, fundamentals, regime, sentiment_score,
                                current_close, vol_20),
        )
        for role in SPECIALIST_ROLES
    }
    results = await asyncio.gather(
        *(_safe_complete(role, prompts[role]) for role in SPECIALIST_ROLES)
    )
    views = dict(zip(SPECIALIST_ROLES, results))
    votes = {role: parse_vote(text) for role, text in views.items()}

    gate = risk_officer_gate(recommendation, vol_20, regime, days_to_earnings)

    vol_str = f"{vol_20:.2f}" if vol_20 is not None else "N/A"
    risk_facts = (
        f"- 20-day annualized volatility: {vol_str} (extreme above {_EXTREME_VOL})\n"
        f"- Market regime: {regime or 'unknown'}\n"
        f"- Days to earnings: {days_to_earnings if days_to_earnings is not None else 'none scheduled'}\n"
        f"- Deterministic veto triggered: {gate['vetoed']}"
        + (f" ({'; '.join(gate['reasons'])})" if gate["reasons"] else "")
    )
    risk_view = await _safe_complete(
        "risk_officer",
        build_risk_officer_prompt(symbol, recommendation, confidence, views, risk_facts),
    )

    # Did any specialist actually produce output? If every LLM call failed (e.g. a
    # 429 rate-limit), the committee did NOT deliberate — say so rather than implying
    # an endorsement. The deterministic veto still holds (it's code, not the LLM).
    llm_available = any((v or "").strip() for v in views.values())

    final = "HOLD" if gate["vetoed"] else recommendation
    return {
        "views": views,
        "votes": votes,
        "risk_officer": risk_view,
        "vetoed": gate["vetoed"],
        "veto_reasons": gate["reasons"],
        "engine_recommendation": recommendation,
        "final_recommendation": final,
        "llm_available": llm_available,
    }
