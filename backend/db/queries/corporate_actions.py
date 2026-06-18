import asyncpg


async def upsert_corporate_actions(
    conn: asyncpg.Connection, symbol: str, actions: list[dict]
) -> int:
    if not actions:
        return 0
    stmt = """
        INSERT INTO corporate_actions (symbol, action_date, action_type, ratio, amount)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (symbol, action_date, action_type) DO UPDATE SET
            ratio  = EXCLUDED.ratio,
            amount = EXCLUDED.amount
    """
    data = [
        (symbol, a["action_date"], a["action_type"], a.get("ratio"), a.get("amount"))
        for a in actions
    ]
    await conn.executemany(stmt, data)
    return len(data)


async def get_corporate_actions(
    conn: asyncpg.Connection, symbol: str, limit: int = 100
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT action_date, action_type, ratio, amount
        FROM corporate_actions
        WHERE symbol = $1
        ORDER BY action_date DESC
        LIMIT $2
        """,
        symbol, limit,
    )


async def get_splits(conn: asyncpg.Connection, symbol: str) -> list[tuple]:
    """Split + bonus events as [(date, ratio)], oldest first — for back-adjustment."""
    rows = await conn.fetch(
        """
        SELECT action_date, ratio
        FROM corporate_actions
        WHERE symbol = $1 AND action_type IN ('split', 'bonus') AND ratio IS NOT NULL
        ORDER BY action_date
        """,
        symbol,
    )
    return [(r["action_date"], float(r["ratio"])) for r in rows]
