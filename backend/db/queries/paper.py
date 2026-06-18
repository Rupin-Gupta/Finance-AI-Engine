import asyncpg

DEFAULT_PORTFOLIO = "default"


async def get_or_create_portfolio(
    conn: asyncpg.Connection, starting_cash: float, name: str = DEFAULT_PORTFOLIO
) -> asyncpg.Record:
    row = await conn.fetchrow("SELECT * FROM paper_portfolio WHERE name = $1", name)
    if row is None:
        row = await conn.fetchrow(
            """
            INSERT INTO paper_portfolio (name, starting_cash, cash)
            VALUES ($1, $2, $2)
            RETURNING *
            """,
            name, float(starting_cash),
        )
    return row


async def update_cash(conn: asyncpg.Connection, cash: float, name: str = DEFAULT_PORTFOLIO) -> None:
    await conn.execute(
        "UPDATE paper_portfolio SET cash = $2, updated_at = now() WHERE name = $1",
        name, float(cash),
    )


async def get_positions(conn: asyncpg.Connection, name: str = DEFAULT_PORTFOLIO) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT symbol, quantity, avg_cost FROM paper_positions WHERE portfolio = $1 ORDER BY symbol",
        name,
    )


async def upsert_position(
    conn: asyncpg.Connection, symbol: str, quantity: float, avg_cost: float,
    name: str = DEFAULT_PORTFOLIO,
) -> None:
    await conn.execute(
        """
        INSERT INTO paper_positions (portfolio, symbol, quantity, avg_cost)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (portfolio, symbol) DO UPDATE SET
            quantity = EXCLUDED.quantity, avg_cost = EXCLUDED.avg_cost, updated_at = now()
        """,
        name, symbol, float(quantity), float(avg_cost),
    )


async def delete_position(conn: asyncpg.Connection, symbol: str, name: str = DEFAULT_PORTFOLIO) -> None:
    await conn.execute(
        "DELETE FROM paper_positions WHERE portfolio = $1 AND symbol = $2", name, symbol
    )


async def insert_trade(conn: asyncpg.Connection, trade: dict, name: str = DEFAULT_PORTFOLIO) -> None:
    await conn.execute(
        """
        INSERT INTO paper_trades (portfolio, symbol, side, quantity, price, fee, realized_pnl)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        name, trade["symbol"], trade["side"], float(trade["quantity"]),
        float(trade["price"]), float(trade["fee"]),
        float(trade["realized_pnl"]) if trade["realized_pnl"] is not None else None,
    )


async def list_trades(
    conn: asyncpg.Connection, limit: int = 100, name: str = DEFAULT_PORTFOLIO
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT symbol, side, quantity, price, fee, realized_pnl, ts
        FROM paper_trades WHERE portfolio = $1 ORDER BY ts DESC LIMIT $2
        """,
        name, limit,
    )


async def reset_portfolio(
    conn: asyncpg.Connection, starting_cash: float, name: str = DEFAULT_PORTFOLIO
) -> None:
    await conn.execute("DELETE FROM paper_positions WHERE portfolio = $1", name)
    await conn.execute("DELETE FROM paper_trades WHERE portfolio = $1", name)
    await conn.execute("DELETE FROM paper_equity_history WHERE portfolio = $1", name)
    await conn.execute(
        """
        INSERT INTO paper_portfolio (name, starting_cash, cash)
        VALUES ($1, $2, $2)
        ON CONFLICT (name) DO UPDATE SET
            starting_cash = EXCLUDED.starting_cash, cash = EXCLUDED.cash, updated_at = now()
        """,
        name, float(starting_cash),
    )


async def insert_equity_snapshot(
    conn: asyncpg.Connection, metrics: dict, name: str = DEFAULT_PORTFOLIO
) -> None:
    """Append one equity-curve point (from paper_trading.portfolio_metrics)."""
    await conn.execute(
        """
        INSERT INTO paper_equity_history (portfolio, equity, cash, positions_value, total_return)
        VALUES ($1, $2, $3, $4, $5)
        """,
        name,
        float(metrics["equity"]),
        float(metrics["cash"]),
        float(metrics["positions_value"]),
        metrics.get("total_return"),
    )


async def get_equity_history(
    conn: asyncpg.Connection, limit: int = 365, name: str = DEFAULT_PORTFOLIO
) -> list[asyncpg.Record]:
    """Equity-curve points oldest→newest (last `limit` snapshots)."""
    rows = await conn.fetch(
        """
        SELECT ts, equity, cash, positions_value, total_return
        FROM paper_equity_history WHERE portfolio = $1 ORDER BY ts DESC LIMIT $2
        """,
        name, limit,
    )
    return list(reversed(rows))
