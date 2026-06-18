import asyncpg


async def insert_alert(conn: asyncpg.Connection, symbol: str, alert_type: str,
                        value: float, threshold: float) -> str:
    row = await conn.fetchrow(
        """
        INSERT INTO alerts (symbol, alert_type, value, threshold, detected_at)
        VALUES ($1, $2, $3, $4, now()) RETURNING id
        """,
        symbol, alert_type, value, threshold,
    )
    return str(row["id"])


async def get_alerts_since(conn: asyncpg.Connection, since) -> list[asyncpg.Record]:
    """Alerts detected strictly after `since`, oldest first. Used by the live stream."""
    return await conn.fetch(
        """
        SELECT id, symbol, alert_type, value, threshold, detected_at
        FROM alerts
        WHERE detected_at > $1
        ORDER BY detected_at
        """,
        since,
    )


async def list_alerts(conn: asyncpg.Connection, symbol: str | None = None,
                       limit: int = 50) -> list[asyncpg.Record]:
    if symbol:
        return await conn.fetch(
            "SELECT * FROM alerts WHERE symbol=$1 ORDER BY detected_at DESC LIMIT $2", symbol, limit
        )
    return await conn.fetch("SELECT * FROM alerts ORDER BY detected_at DESC LIMIT $1", limit)
