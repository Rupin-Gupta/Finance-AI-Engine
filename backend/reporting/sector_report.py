import logging

import asyncpg

from backend.llm.client import get_llm_client
from backend.llm.prompts import build_report_prompt
from backend.db.queries.chat import append_chat_history

logger = logging.getLogger(__name__)


async def _latest_analytics_per_symbol(conn: asyncpg.Connection) -> list[dict]:
    """Latest analytics row for each symbol, joined with stock sector."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (a.symbol)
            a.symbol,
            s.sector,
            a.sma_20,
            a.ema_20,
            a.rsi_14,
            a.volatility_20,
            a.momentum_10,
            a.timestamp
        FROM analytics a
        LEFT JOIN stocks s ON s.symbol = a.symbol
        ORDER BY a.symbol, a.timestamp DESC
        """
    )
    return [dict(r) for r in rows]


async def run_sector_report(conn: asyncpg.Connection) -> list[str]:
    """
    For each sector with data: build metrics dict → LLM prompt → store in chat_history.
    Returns list of chat_history IDs written.
    """
    rows = await _latest_analytics_per_symbol(conn)
    if not rows:
        return []

    # Group by sector (None → "Unknown")
    sectors: dict[str, list[dict]] = {}
    for row in rows:
        sector = row.get("sector") or "Unknown"
        sectors.setdefault(sector, []).append(row)

    client = get_llm_client()
    chat_ids: list[str] = []

    for sector, symbols in sectors.items():
        for row in symbols:
            try:
                metrics = {
                    k: round(float(v), 4) if v is not None else "N/A"
                    for k, v in {
                        "SMA(20)":      row["sma_20"],
                        "EMA(20)":      row["ema_20"],
                        "RSI(14)":      row["rsi_14"],
                        "Volatility":   row["volatility_20"],
                        "Momentum(10)": row["momentum_10"],
                    }.items()
                }
                prompt = build_report_prompt(f"{row['symbol']} ({sector})", metrics)
                report_text = await client.complete(prompt)
                chat_id = await append_chat_history(
                    conn,
                    query=f"Sector report: {row['symbol']} ({sector})",
                    response=report_text,
                    sources=[],
                )
                chat_ids.append(chat_id)
            except Exception as exc:
                logger.error("sector_report failed for %s (%s): %s", row["symbol"], sector, exc)

    return chat_ids
