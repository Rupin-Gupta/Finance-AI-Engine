import asyncpg


async def ensure_stocks(conn: asyncpg.Connection, symbols: list[str]) -> int:
    """Insert stock symbols needed by market_data FK constraints."""
    unique_symbols = sorted({symbol.upper() for symbol in symbols if symbol.strip()})
    if not unique_symbols:
        return 0

    await conn.executemany(
        "INSERT INTO stocks (symbol) VALUES ($1) ON CONFLICT (symbol) DO NOTHING",
        [(symbol,) for symbol in unique_symbols],
    )
    return len(unique_symbols)
