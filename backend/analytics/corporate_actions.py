"""Corporate actions: split-adjustment math (pure) + yfinance fetcher.

A split/bonus silently corrupts raw price history — a 2:1 split halves the close,
which technical signals read as a -50% crash and backtests as a huge loss. The
fix is to back-adjust historical prices by the cumulative split ratio that occurred
*after* each date so the series is continuous.

NOTE: market ingest uses yfinance with auto_adjust=True (see ingest/market.py), so
freshly-ingested OHLCV is already split/dividend adjusted — do NOT double-adjust it.
These helpers are for raw series from other sources (e.g. Finnhub) or pre-fix data,
and to surface the actions themselves.
"""
import asyncio
from datetime import date


def split_adjustment_divisor(target: date, splits: list[tuple[date, float]]) -> float:
    """Cumulative split ratio for splits occurring strictly AFTER `target`.

    Back-adjust a raw price at `target` by dividing it by this divisor so it lines
    up with post-split prices. Splits on/before `target` don't affect it.
    """
    divisor = 1.0
    for ex_date, ratio in splits:
        if ratio and ex_date > target:
            divisor *= ratio
    return divisor


def apply_split_adjustment(
    series: list[tuple[date, float]], splits: list[tuple[date, float]]
) -> list[tuple[date, float]]:
    """Back-adjust a [(date, price)] series for splits. Returns adjusted series.

    No-op when there are no splits. Idempotent only on RAW input — never apply to
    already-adjusted data.
    """
    if not splits:
        return [(d, float(p)) for d, p in series]
    return [
        (d, round(float(p) / split_adjustment_divisor(d, splits), 6))
        for d, p in series
    ]


def _fetch(symbol: str) -> list[dict]:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    actions: list[dict] = []

    splits = getattr(ticker, "splits", None)
    if splits is not None and len(splits):
        for ts, ratio in splits.items():
            if ratio:
                actions.append({
                    "action_date": ts.date(),
                    "action_type": "split",
                    "ratio": float(ratio),
                    "amount": None,
                })

    dividends = getattr(ticker, "dividends", None)
    if dividends is not None and len(dividends):
        for ts, amt in dividends.items():
            if amt:
                actions.append({
                    "action_date": ts.date(),
                    "action_type": "dividend",
                    "ratio": None,
                    "amount": float(amt),
                })

    return actions


async def fetch_corporate_actions(symbol: str) -> list[dict]:
    """Fetch splits + dividends from yfinance without blocking the event loop."""
    return await asyncio.to_thread(_fetch, symbol.upper())
