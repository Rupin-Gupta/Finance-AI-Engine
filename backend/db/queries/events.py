"""market_events table access (R8)."""
import asyncpg


async def upsert_events(conn: asyncpg.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = """
        INSERT INTO market_events (event_date, event_type, region, impact, title, source)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (event_date, event_type, region) DO UPDATE SET
            impact = EXCLUDED.impact,
            title  = EXCLUDED.title,
            source = EXCLUDED.source
    """
    data = [
        (r["event_date"], r["event_type"], r["region"], r["impact"], r["title"], r.get("source"))
        for r in rows
    ]
    await conn.executemany(stmt, data)
    return len(data)


async def get_upcoming_events(conn: asyncpg.Connection, days: int = 90,
                              region: str | None = None) -> list[asyncpg.Record]:
    """Upcoming events from today through today+days, nearest first.

    region None → all; otherwise that region plus GLOBAL (which gates every market).
    """
    if region:
        return await conn.fetch(
            """
            SELECT event_date, event_type, region, impact, title, source
            FROM market_events
            WHERE event_date >= CURRENT_DATE AND event_date <= CURRENT_DATE + $1::int
              AND region IN ($2, 'GLOBAL')
            ORDER BY event_date
            """,
            days, region,
        )
    return await conn.fetch(
        """
        SELECT event_date, event_type, region, impact, title, source
        FROM market_events
        WHERE event_date >= CURRENT_DATE AND event_date <= CURRENT_DATE + $1::int
        ORDER BY event_date
        """,
        days,
    )
