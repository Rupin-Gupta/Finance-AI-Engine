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


def build_decision_prompt(symbol: str, recommendation: str, confidence: float,
                           risk_level: str, signals_json: dict,
                           sentiment_score: float | None,
                           predicted_close: float | None,
                           current_close: float | None) -> str:
    signal_lines = "\n".join(
        f"- {name}: score={v['score']:+.0f}, value={v['value']}, label={v['label']}"
        for name, v in signals_json.items()
    )
    return f"""You are a senior equity analyst. Explain the following trading signal for {symbol} in plain English.

RECOMMENDATION: {recommendation} (confidence: {confidence:.0%}, risk: {risk_level})
CURRENT PRICE: ${current_close if current_close else 'N/A'}
7-DAY FORECAST: ${predicted_close:.2f if predicted_close else 'N/A'}
SENTIMENT SCORE: {sentiment_score if sentiment_score is not None else 'N/A'} (range -1 to +1)

SIGNAL BREAKDOWN:
{signal_lines}

Write 3-4 sentences for an investment committee. Reference the specific signals that drove the {recommendation} call. Be factual and avoid hype."""
