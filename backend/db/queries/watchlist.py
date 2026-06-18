import asyncpg


async def upsert_watchlist_item(conn: asyncpg.Connection, item: dict) -> asyncpg.Record:
    """Insert or update a watchlist entry on symbol. Returns the stored row."""
    return await conn.fetchrow(
        """
        INSERT INTO watchlist (symbol, quantity, cost_basis, note)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (symbol) DO UPDATE SET
            quantity   = EXCLUDED.quantity,
            cost_basis = EXCLUDED.cost_basis,
            note       = EXCLUDED.note,
            updated_at = now()
        RETURNING symbol, quantity, cost_basis, note, created_at, updated_at
        """,
        item["symbol"],
        item.get("quantity"),
        item.get("cost_basis"),
        item.get("note"),
    )


async def list_watchlist(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT symbol, quantity, cost_basis, note, created_at, updated_at "
        "FROM watchlist ORDER BY symbol"
    )


async def delete_watchlist_item(conn: asyncpg.Connection, symbol: str) -> bool:
    """Delete a watchlist entry. Returns True if a row was removed."""
    result = await conn.execute("DELETE FROM watchlist WHERE symbol = $1", symbol)
    # asyncpg returns a status string like "DELETE 1"
    return result.rsplit(" ", 1)[-1] != "0"
