import asyncpg
from datetime import datetime


async def upsert_market_data(conn: asyncpg.Connection, rows: list[dict]) -> int:
    """Upsert OHLCV rows on (symbol, timestamp). Returns row count."""
    stmt = """
        INSERT INTO market_data (symbol, timestamp, open, high, low, close, volume)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (symbol, timestamp) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
            close = EXCLUDED.close, volume = EXCLUDED.volume
    """
    data = [(r["symbol"], r["timestamp"], r["open"], r["high"],
             r["low"], r["close"], r["volume"]) for r in rows]
    await conn.executemany(stmt, data)
    return len(data)


async def get_ohlcv(conn: asyncpg.Connection, symbol: str,
                    start: datetime, end: datetime) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT * FROM market_data WHERE symbol=$1 AND timestamp BETWEEN $2 AND $3 ORDER BY timestamp",
        symbol, start, end,
    )
