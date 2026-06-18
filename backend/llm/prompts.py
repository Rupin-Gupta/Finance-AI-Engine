def build_rag_prompt(query: str, context_chunks: list[str]) -> str:
    context = "\n\n".join(f"[{i+1}] {c}" for i, c in enumerate(context_chunks))
    return f"""You are a financial analyst assistant. Answer the question using ONLY the context below.
If the context is insufficient, say so. Be concise and factual.

CONTEXT:
{context}

QUESTION: {query}

ANSWER:"""


def build_report_prompt(symbol: str, metrics: dict) -> str:
    lines = "\n".join(f"- {k}: {v}" for k, v in metrics.items())
    return f"""Generate a concise financial summary for {symbol} based on these metrics:
{lines}

Write 2-3 sentences suitable for an executive briefing. Be specific and data-driven."""


def _signal_lines(signals_json: dict) -> str:
    return "\n".join(
        f"- {name}: score={v['score']:+.0f}, value={v['value']}, label={v['label']}"
        for name, v in signals_json.items()
    )


def _price_block(symbol: str, current_close: float | None, predicted_close: float | None,
                 sentiment_score: float | None, recommendation: str, confidence: float,
                 risk_level: str) -> str:
    current_str  = f"${current_close:.2f}"  if current_close  is not None else "N/A"
    forecast_str = f"${predicted_close:.2f}" if predicted_close is not None else "N/A"
    sent_str     = f"{sentiment_score:.3f}"  if sentiment_score is not None else "N/A"
    return (
        f"SYMBOL: {symbol}\n"
        f"RECOMMENDATION: {recommendation} (confidence: {confidence:.0%}, risk: {risk_level})\n"
        f"CURRENT PRICE: {current_str}  |  7-DAY FORECAST: {forecast_str}\n"
        f"SENTIMENT SCORE: {sent_str} (range -1 to +1)"
    )


def build_bull_prompt(symbol: str, recommendation: str, confidence: float,
                      risk_level: str, signals_json: dict,
                      sentiment_score: float | None, predicted_close: float | None,
                      current_close: float | None) -> str:
    return f"""You are a bullish equity analyst. Your job is to make the strongest possible case for BUYING {symbol}.

{_price_block(symbol, current_close, predicted_close, sentiment_score, recommendation, confidence, risk_level)}

SIGNAL BREAKDOWN:
{_signal_lines(signals_json)}

Write 3-4 sentences presenting only the bullish evidence. Cite the specific signals that support buying. Be direct and data-driven."""


def build_bear_prompt(symbol: str, recommendation: str, confidence: float,
                      risk_level: str, signals_json: dict,
                      sentiment_score: float | None, predicted_close: float | None,
                      current_close: float | None) -> str:
    return f"""You are a bearish equity analyst. Your job is to make the strongest possible case for AVOIDING or SELLING {symbol}.

{_price_block(symbol, current_close, predicted_close, sentiment_score, recommendation, confidence, risk_level)}

SIGNAL BREAKDOWN:
{_signal_lines(signals_json)}

Write 3-4 sentences presenting only the bearish risks and warning signs. Cite the specific signals that support caution. Be direct and data-driven."""


def build_synthesis_prompt(symbol: str, recommendation: str, confidence: float,
                            risk_level: str, bull_case: str, bear_case: str,
                            days_to_earnings: int | None) -> str:
    earnings_note = (
        f"\nNOTE: Earnings are {days_to_earnings} days away — binary event risk is elevated."
        if days_to_earnings is not None and days_to_earnings <= 14
        else ""
    )
    return f"""You are a senior portfolio manager adjudicating competing analyses for {symbol}.

BULL CASE:
{bull_case}

BEAR CASE:
{bear_case}

ENGINE VERDICT: {recommendation} at {confidence:.0%} confidence, risk level {risk_level}.{earnings_note}

Write 3-4 sentences delivering a balanced final judgment. State the primary reason the engine reached {recommendation}, acknowledge the strongest counterargument, and note any key risk. Be concise and investment-committee ready."""


def build_decision_prompt(symbol: str, recommendation: str, confidence: float,
                           risk_level: str, signals_json: dict,
                           sentiment_score: float | None,
                           predicted_close: float | None,
                           current_close: float | None) -> str:
    """Single-agent fallback prompt (used when multi-agent is disabled)."""
    current_str  = f"${current_close:.2f}"  if current_close  is not None else "N/A"
    forecast_str = f"${predicted_close:.2f}" if predicted_close is not None else "N/A"
    return f"""You are a senior equity analyst. Explain the following trading signal for {symbol} in plain English.

RECOMMENDATION: {recommendation} (confidence: {confidence:.0%}, risk: {risk_level})
CURRENT PRICE: {current_str}
7-DAY FORECAST: {forecast_str}
SENTIMENT SCORE: {sentiment_score if sentiment_score is not None else 'N/A'} (range -1 to +1)

SIGNAL BREAKDOWN:
{_signal_lines(signals_json)}

Write 3-4 sentences for an investment committee. Reference the specific signals that drove the {recommendation} call. Be factual and avoid hype."""


# ---------------------------------------------------------------------------
# R10: investment committee — specialist + risk-officer prompts
# ---------------------------------------------------------------------------

_SPECIALIST_BRIEFS = {
    "technical": (
        "You are the TECHNICAL ANALYST on an investment committee. Judge ONLY price action: "
        "trend vs moving averages, RSI, momentum, EMA crossover, volume confirmation."
    ),
    "fundamental": (
        "You are the FUNDAMENTAL ANALYST on an investment committee. Judge ONLY business value: "
        "valuation multiples, earnings, margins, analyst targets."
    ),
    "macro": (
        "You are the MACRO STRATEGIST on an investment committee. Judge ONLY the market environment: "
        "the current regime, volatility conditions, and how they affect this trade's odds."
    ),
    "sentiment": (
        "You are the SENTIMENT ANALYST on an investment committee. Judge ONLY crowd positioning: "
        "news and social sentiment, its strength, and whether it is confirming or contrarian."
    ),
}


def build_specialist_prompt(role: str, symbol: str, recommendation: str,
                            signals_json: dict, context: str) -> str:
    brief = _SPECIALIST_BRIEFS[role]
    return f"""{brief}

SYMBOL: {symbol} — engine recommendation under review: {recommendation}

SIGNAL BREAKDOWN:
{_signal_lines(signals_json)}

{context}

In 3-4 sentences, give your view STRICTLY within your specialty, then end with exactly one line:
VOTE: BUY or VOTE: SELL or VOTE: HOLD"""


def build_risk_officer_prompt(symbol: str, recommendation: str, confidence: float,
                              views: dict[str, str], risk_facts: str) -> str:
    view_block = "\n\n".join(
        f"--- {role.upper()} ---\n{text or '(no view — agent unavailable)'}"
        for role, text in views.items()
    )
    return f"""You are the RISK OFFICER of an investment committee with veto authority.
The engine recommends {recommendation} on {symbol} (confidence {confidence:.0%}).

COMMITTEE VIEWS:
{view_block}

RISK FACTS:
{risk_facts}

In 3-4 sentences: weigh the committee's views against the risk facts and state whether you
endorse the recommendation or would reduce/veto it, and why. Be specific about the single
biggest risk."""
