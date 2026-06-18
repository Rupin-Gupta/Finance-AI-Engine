import asyncpg


async def upsert_fundamentals(conn: asyncpg.Connection, row: dict) -> None:
    await conn.execute(
        """
        INSERT INTO fundamentals (
            symbol, market_cap, pe_trailing, pe_forward, peg_ratio,
            eps_trailing, eps_forward, revenue, gross_margins, profit_margins,
            price_to_book, beta, dividend_yield, week_52_high, week_52_low,
            analyst_target, analyst_rating, analyst_count, updated_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17, $18, now()
        )
        ON CONFLICT (symbol) DO UPDATE SET
            market_cap      = EXCLUDED.market_cap,
            pe_trailing     = EXCLUDED.pe_trailing,
            pe_forward      = EXCLUDED.pe_forward,
            peg_ratio       = EXCLUDED.peg_ratio,
            eps_trailing    = EXCLUDED.eps_trailing,
            eps_forward     = EXCLUDED.eps_forward,
            revenue         = EXCLUDED.revenue,
            gross_margins   = EXCLUDED.gross_margins,
            profit_margins  = EXCLUDED.profit_margins,
            price_to_book   = EXCLUDED.price_to_book,
            beta            = EXCLUDED.beta,
            dividend_yield  = EXCLUDED.dividend_yield,
            week_52_high    = EXCLUDED.week_52_high,
            week_52_low     = EXCLUDED.week_52_low,
            analyst_target  = EXCLUDED.analyst_target,
            analyst_rating  = EXCLUDED.analyst_rating,
            analyst_count   = EXCLUDED.analyst_count,
            updated_at      = now()
        """,
        row.get("symbol"),
        row.get("market_cap"),
        row.get("pe_trailing"),
        row.get("pe_forward"),
        row.get("peg_ratio"),
        row.get("eps_trailing"),
        row.get("eps_forward"),
        row.get("revenue"),
        row.get("gross_margins"),
        row.get("profit_margins"),
        row.get("price_to_book"),
        row.get("beta"),
        row.get("dividend_yield"),
        row.get("week_52_high"),
        row.get("week_52_low"),
        row.get("analyst_target"),
        row.get("analyst_rating"),
        row.get("analyst_count"),
    )


async def get_fundamentals(conn: asyncpg.Connection, symbol: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "SELECT * FROM fundamentals WHERE symbol = $1",
        symbol,
    )


async def upsert_earnings(conn: asyncpg.Connection, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = """
        INSERT INTO earnings_calendar (symbol, earnings_date, eps_estimate, eps_actual, surprise_pct)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (symbol, earnings_date) DO UPDATE SET
            eps_estimate = EXCLUDED.eps_estimate,
            eps_actual   = EXCLUDED.eps_actual,
            surprise_pct = EXCLUDED.surprise_pct
    """
    data = [
        (r["symbol"], r["earnings_date"], r.get("eps_estimate"), r.get("eps_actual"), r.get("surprise_pct"))
        for r in rows
    ]
    await conn.executemany(stmt, data)
    return len(data)


async def get_earnings(conn: asyncpg.Connection, symbol: str, limit: int = 10) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT earnings_date, eps_estimate, eps_actual, surprise_pct
        FROM earnings_calendar
        WHERE symbol = $1
        ORDER BY earnings_date DESC
        LIMIT $2
        """,
        symbol, limit,
    )


async def get_market_caps(conn: asyncpg.Connection, symbols: list[str]) -> dict[str, float]:
    """Return {symbol: market_cap} for symbols with a stored cap (R6 exposure buckets)."""
    if not symbols:
        return {}
    rows = await conn.fetch(
        "SELECT symbol, market_cap FROM fundamentals WHERE symbol = ANY($1::text[]) AND market_cap IS NOT NULL",
        symbols,
    )
    return {r["symbol"]: float(r["market_cap"]) for r in rows}
