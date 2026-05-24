import asyncpg

from backend.ingest.market import fetch_ohlcv
from backend.db.queries.market_data import upsert_market_data
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.stocks import ensure_stocks

REQUIRED_OHLCV_FIELDS = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for symbol in symbols:
        clean = symbol.strip().upper()
        if clean and clean not in seen:
            normalized.append(clean)
            seen.add(clean)
    if not normalized:
        raise ValueError("At least one market symbol is required")
    return normalized


def _validate_rows(rows: list[dict]) -> list[dict]:
    valid_rows = []
    for row in rows:
        missing = REQUIRED_OHLCV_FIELDS.difference(row)
        if missing:
            raise ValueError(f"OHLCV row missing fields: {sorted(missing)}")
        if any(row[field] is None for field in REQUIRED_OHLCV_FIELDS):
            raise ValueError("OHLCV row contains null required fields")
        valid_rows.append(row)
    return valid_rows


def _dedupe_rows(rows: list[dict]) -> list[dict]:
    by_key = {}
    for row in rows:
        by_key[(row["symbol"], row["timestamp"])] = row
    return list(by_key.values())


async def run_market_ingest(conn: asyncpg.Connection, symbols: list[str],
                             period: str = "5d", interval: str = "1d") -> str:
    """ETL: extract, validate, dedupe, normalize, and upsert market data."""
    job_id = await create_job(conn, "market_ingest")
    try:
        normalized_symbols = _normalize_symbols(symbols)
        await ensure_stocks(conn, normalized_symbols)

        for symbol in normalized_symbols:
            rows = await fetch_ohlcv(symbol, period=period, interval=interval)
            rows = _dedupe_rows(_validate_rows(rows))
            if rows:
                await upsert_market_data(conn, rows)
        await update_job_status(conn, job_id, "completed")
    except Exception as exc:
        await update_job_status(conn, job_id, "failed", error=str(exc))
        raise
    return job_id
