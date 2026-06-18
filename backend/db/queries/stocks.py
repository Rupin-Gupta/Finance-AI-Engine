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


async def update_stock_names(conn: asyncpg.Connection, name_map: dict[str, str]) -> None:
    """Write company names into stocks.name (used for news headline matching)."""
    data = [
        (name.strip(), symbol)
        for symbol, name in name_map.items()
        if name and name.strip()
    ]
    if not data:
        return
    await conn.executemany(
        "UPDATE stocks SET name = $1 WHERE symbol = $2 AND (name IS NULL OR name != $1)",
        data,
    )


async def get_symbol_names(
    conn: asyncpg.Connection, symbols: list[str]
) -> dict[str, str]:
    """Return {symbol: company_name} for symbols that have a name in stocks table."""
    if not symbols:
        return {}
    rows = await conn.fetch(
        "SELECT symbol, name FROM stocks WHERE symbol = ANY($1::text[]) AND name IS NOT NULL",
        symbols,
    )
    return {r["symbol"]: r["name"] for r in rows}


async def update_stock_sectors(conn: asyncpg.Connection, sector_map: dict[str, str]) -> None:
    """Write sectors into stocks.sector (populated by fundamentals_run; used by R6)."""
    data = [
        (sector.strip(), symbol)
        for symbol, sector in sector_map.items()
        if sector and sector.strip()
    ]
    if not data:
        return
    await conn.executemany(
        "UPDATE stocks SET sector = $1 WHERE symbol = $2 AND (sector IS NULL OR sector != $1)",
        data,
    )


async def get_symbol_sectors(
    conn: asyncpg.Connection, symbols: list[str]
) -> dict[str, str]:
    """Return {symbol: sector} for symbols that have a sector in stocks table."""
    if not symbols:
        return {}
    rows = await conn.fetch(
        "SELECT symbol, sector FROM stocks WHERE symbol = ANY($1::text[]) AND sector IS NOT NULL",
        symbols,
    )
    return {r["symbol"]: r["sector"] for r in rows}
