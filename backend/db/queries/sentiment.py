import asyncpg
from datetime import date


async def upsert_sentiment(conn: asyncpg.Connection, rows: list[dict]) -> int:
    stmt = """
        INSERT INTO sentiment (symbol, date, score, headline_count, source)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (symbol, date) DO UPDATE SET
            score          = EXCLUDED.score,
            headline_count = EXCLUDED.headline_count,
            source         = EXCLUDED.source,
            created_at     = now()
    """
    data = [
        (r["symbol"], r["date"], float(r["score"]), int(r["headline_count"]), r.get("source", "yahoo_rss"))
        for r in rows
    ]
    await conn.executemany(stmt, data)
    return len(data)


async def get_latest_sentiment(conn: asyncpg.Connection, symbol: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "SELECT * FROM sentiment WHERE symbol=$1 ORDER BY date DESC LIMIT 1",
        symbol,
    )


async def get_sentiment_history(
    conn: asyncpg.Connection, symbol: str, days: int = 30
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT date, score, headline_count
        FROM sentiment
        WHERE symbol=$1
        ORDER BY date DESC
        LIMIT $2
        """,
        symbol, days,
    )
