import asyncpg
from datetime import date, datetime


async def upsert_sentiment(conn: asyncpg.Connection, rows: list[dict]) -> int:
    stmt = """
        INSERT INTO sentiment (symbol, date, score, headline_count, source)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (symbol, date, source) DO UPDATE SET
            score          = EXCLUDED.score,
            headline_count = EXCLUDED.headline_count,
            created_at     = now()
    """
    data = [
        (r["symbol"], r["date"], float(r["score"]), int(r["headline_count"]), r.get("source", "yahoo_finance"))
        for r in rows
    ]
    await conn.executemany(stmt, data)
    return len(data)


async def get_latest_sentiment(conn: asyncpg.Connection, symbol: str) -> asyncpg.Record | None:
    """Return count-weighted aggregated sentiment for the most recent date."""
    return await conn.fetchrow(
        """
        SELECT date,
               ROUND(
                   (SUM(score * headline_count) / NULLIF(SUM(headline_count), 0))::numeric,
                   4
               )                        AS score,
               SUM(headline_count)      AS headline_count
        FROM sentiment
        WHERE symbol = $1
          AND date = (SELECT MAX(date) FROM sentiment WHERE symbol = $1)
        GROUP BY date
        """,
        symbol,
    )


async def get_latest_sentiment_multi(
    conn: asyncpg.Connection, symbols: list[str]
) -> dict[str, float]:
    """Return {symbol: latest-date count-weighted score} for the given symbols (one query)."""
    if not symbols:
        return {}
    rows = await conn.fetch(
        """
        WITH latest AS (
            SELECT symbol, MAX(date) AS d
            FROM sentiment
            WHERE symbol = ANY($1)
            GROUP BY symbol
        )
        SELECT s.symbol,
               ROUND(
                   (SUM(s.score * s.headline_count) / NULLIF(SUM(s.headline_count), 0))::numeric,
                   4
               ) AS score
        FROM sentiment s
        JOIN latest l ON l.symbol = s.symbol AND l.d = s.date
        GROUP BY s.symbol
        """,
        symbols,
    )
    return {r["symbol"]: float(r["score"]) for r in rows if r["score"] is not None}


async def get_sentiment_history(
    conn: asyncpg.Connection, symbol: str, days: int = 30
) -> list[asyncpg.Record]:
    """Return per-day count-weighted aggregated sentiment, most recent first."""
    return await conn.fetch(
        """
        SELECT date,
               ROUND(
                   (SUM(score * headline_count) / NULLIF(SUM(headline_count), 0))::numeric,
                   4
               )                        AS score,
               SUM(headline_count)      AS headline_count
        FROM sentiment
        WHERE symbol = $1
        GROUP BY date
        ORDER BY date DESC
        LIMIT $2
        """,
        symbol, days,
    )


async def get_sentiment_by_date_range(
    conn: asyncpg.Connection,
    symbol: str,
    start: date,
    end: date,
) -> dict[date, float]:
    """Return {date: count-weighted score} for a date range (for backtesting)."""
    rows = await conn.fetch(
        """
        SELECT date,
               ROUND(
                   (SUM(score * headline_count) / NULLIF(SUM(headline_count), 0))::numeric,
                   4
               ) AS score
        FROM sentiment
        WHERE symbol = $1 AND date BETWEEN $2 AND $3
        GROUP BY date
        ORDER BY date
        """,
        symbol, start, end,
    )
    # The count-weighted aggregate can be NULL (e.g. all headline_counts zero) — skip those.
    return {r["date"]: float(r["score"]) for r in rows if r["score"] is not None}


async def get_sentiment_sources(
    conn: asyncpg.Connection, symbol: str
) -> list[asyncpg.Record]:
    """Return per-source scores for the most recent date (for dashboard breakdown)."""
    return await conn.fetch(
        """
        SELECT source,
               score,
               headline_count,
               date
        FROM sentiment
        WHERE symbol = $1
          AND date = (SELECT MAX(date) FROM sentiment WHERE symbol = $1)
        ORDER BY source
        """,
        symbol,
    )
