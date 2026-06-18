"""Fetch fundamental data and earnings calendar from yfinance."""
import asyncio
import logging
from datetime import date

import yfinance as yf

logger = logging.getLogger(__name__)

_INFO_FIELDS = {
    "marketCap": "market_cap",
    "trailingPE": "pe_trailing",
    "forwardPE": "pe_forward",
    "pegRatio": "peg_ratio",
    "trailingEps": "eps_trailing",
    "forwardEps": "eps_forward",
    "totalRevenue": "revenue",
    "grossMargins": "gross_margins",
    "profitMargins": "profit_margins",
    "priceToBook": "price_to_book",
    "beta": "beta",
    "dividendYield": "dividend_yield",
    "fiftyTwoWeekHigh": "week_52_high",
    "fiftyTwoWeekLow": "week_52_low",
    "targetMeanPrice": "analyst_target",
    "recommendationKey": "analyst_rating",
    "numberOfAnalystOpinions": "analyst_count",
}


def _fetch_fundamentals_sync(symbol: str) -> dict:
    info = yf.Ticker(symbol).info
    row: dict = {"symbol": symbol}
    for src_key, dst_key in _INFO_FIELDS.items():
        val = info.get(src_key)
        if val is not None:
            try:
                if dst_key in ("market_cap", "revenue", "analyst_count"):
                    row[dst_key] = int(val)
                elif dst_key == "analyst_rating":
                    row[dst_key] = str(val)
                else:
                    row[dst_key] = float(val)
            except (TypeError, ValueError):
                row[dst_key] = None
        else:
            row[dst_key] = None
    # company name — used to populate stocks.name for news matching
    row["name"] = info.get("shortName") or info.get("longName") or None
    # sector — used to populate stocks.sector for portfolio risk (R6) + sector reports
    row["sector"] = info.get("sector") or None
    return row


def _fetch_earnings_sync(symbol: str) -> list[dict]:
    ticker = yf.Ticker(symbol)
    try:
        df = ticker.earnings_dates
    except Exception:
        return []
    if df is None or df.empty:
        return []

    rows = []
    for idx, row in df.iterrows():
        try:
            earnings_date = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
            eps_estimate = row.get("EPS Estimate")
            eps_actual = row.get("Reported EPS")
            surprise_pct = row.get("Surprise(%)")

            def _safe_float(v):
                try:
                    f = float(v)
                    import math
                    return None if math.isnan(f) else f
                except (TypeError, ValueError):
                    return None

            rows.append({
                "symbol": symbol,
                "earnings_date": earnings_date,
                "eps_estimate": _safe_float(eps_estimate),
                "eps_actual": _safe_float(eps_actual),
                "surprise_pct": _safe_float(surprise_pct),
            })
        except Exception as exc:
            logger.debug("Skipping earnings row for %s: %s", symbol, exc)
    return rows


async def fetch_fundamentals(symbol: str) -> dict:
    return await asyncio.to_thread(_fetch_fundamentals_sync, symbol)


async def fetch_earnings(symbol: str) -> list[dict]:
    return await asyncio.to_thread(_fetch_earnings_sync, symbol)
