import asyncpg
import pandas as pd
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


async def get_closes_by_symbol(
    conn: asyncpg.Connection, symbols: list[str], start: datetime, end: datetime
) -> dict[str, list[tuple]]:
    """Return {symbol: [(date, close), ...]} sorted by date, for entry/exit price resolution."""
    if not symbols:
        return {}
    rows = await conn.fetch(
        """
        SELECT symbol, timestamp::date AS date, close
        FROM market_data
        WHERE symbol = ANY($1) AND timestamp BETWEEN $2 AND $3
        ORDER BY symbol, date
        """,
        symbols, start, end,
    )
    out: dict[str, list[tuple]] = {}
    for r in rows:
        out.setdefault(r["symbol"], []).append((r["date"], float(r["close"])))
    return out


async def get_latest_prices(
    conn: asyncpg.Connection, symbols: list[str]
) -> dict[str, float]:
    """Return {symbol: most-recent close} for the given symbols (one query)."""
    if not symbols:
        return {}
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (symbol) symbol, close
        FROM market_data
        WHERE symbol = ANY($1)
        ORDER BY symbol, timestamp DESC
        """,
        symbols,
    )
    return {r["symbol"]: float(r["close"]) for r in rows}


async def get_prices_multi(
    conn: asyncpg.Connection,
    symbols: list[str],
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Returns a DataFrame (DatetimeIndex, columns=symbols) of daily close prices.
    Symbols with fewer than 20 rows are dropped before returning."""
    rows = await conn.fetch(
        """
        SELECT symbol, timestamp::date AS date, close
        FROM market_data
        WHERE symbol = ANY($1) AND timestamp BETWEEN $2 AND $3
        ORDER BY date
        """,
        symbols, start, end,
    )
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=["symbol", "date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = df["close"].astype(float)  # asyncpg NUMERIC → Decimal breaks float math downstream
    pivot = df.pivot_table(index="date", columns="symbol", values="close", aggfunc="last")

    # drop symbols with sparse data
    pivot = pivot.dropna(axis=1, thresh=20)
    pivot = pivot.ffill().dropna()
    return pivot


async def get_market_breadth(conn: asyncpg.Connection, market: str) -> float | None:
    """Share of a market's symbols whose latest close beats their close 20 bars ago.

    market: 'US' (no .NS/.BO suffix) or 'INDIA' (.NS/.BO). Returns None when no
    symbol has ≥21 stored bars. One query regardless of symbol count (R5 breadth).
    """
    india = market.upper() == "INDIA"
    row = await conn.fetchrow(
        """
        WITH ranked AS (
            SELECT symbol, close,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) AS rn
            FROM market_data
            WHERE ($1 AND (symbol LIKE '%.NS' OR symbol LIKE '%.BO'))
               OR (NOT $1 AND symbol NOT LIKE '%.NS' AND symbol NOT LIKE '%.BO')
        ),
        pairs AS (
            SELECT latest.symbol, latest.close AS latest_close, past.close AS past_close
            FROM ranked latest
            JOIN ranked past ON past.symbol = latest.symbol AND past.rn = 21
            WHERE latest.rn = 1
        )
        SELECT COUNT(*) FILTER (WHERE latest_close > past_close)::float
               / NULLIF(COUNT(*), 0) AS breadth
        FROM pairs
        """,
        india,
    )
    return float(row["breadth"]) if row and row["breadth"] is not None else None


async def get_high_water(conn: asyncpg.Connection, symbols: list[str], days: int = 90) -> dict[str, float]:
    """Highest close per symbol over the trailing window (P3 trailing-stop reference)."""
    if not symbols:
        return {}
    rows = await conn.fetch(
        """
        SELECT symbol, MAX(close)::float AS hw
        FROM market_data
        WHERE symbol = ANY($1) AND timestamp >= now() - ($2::int || ' days')::interval
        GROUP BY symbol
        """,
        symbols, days,
    )
    return {r["symbol"]: r["hw"] for r in rows if r["hw"] is not None}


async def get_latest_volatility(conn: asyncpg.Connection, symbols: list[str]) -> dict[str, float]:
    """{symbol: latest annualized volatility_20} from analytics (one query, P3 stop sizing)."""
    if not symbols:
        return {}
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (symbol) symbol, volatility_20
        FROM analytics
        WHERE symbol = ANY($1) AND volatility_20 IS NOT NULL
        ORDER BY symbol, timestamp DESC
        """,
        symbols,
    )
    return {r["symbol"]: float(r["volatility_20"]) for r in rows}
