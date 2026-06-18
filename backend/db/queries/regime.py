"""market_regime table access (R5)."""
import asyncpg


async def upsert_regime(conn: asyncpg.Connection, row: dict) -> None:
    await conn.execute(
        """
        INSERT INTO market_regime
            (date, market, regime, index_symbol, index_close, sma_50, sma_200,
             vix, realized_vol, breadth_pct, reason)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        ON CONFLICT (date, market) DO UPDATE SET
            regime       = EXCLUDED.regime,
            index_symbol = EXCLUDED.index_symbol,
            index_close  = EXCLUDED.index_close,
            sma_50       = EXCLUDED.sma_50,
            sma_200      = EXCLUDED.sma_200,
            vix          = EXCLUDED.vix,
            realized_vol = EXCLUDED.realized_vol,
            breadth_pct  = EXCLUDED.breadth_pct,
            reason       = EXCLUDED.reason,
            created_at   = now()
        """,
        row["date"], row["market"], row["regime"], row.get("index_symbol"),
        row.get("index_close"), row.get("sma_50"), row.get("sma_200"),
        row.get("vix"), row.get("realized_vol"), row.get("breadth_pct"),
        row.get("reason"),
    )


async def get_latest_regime(conn: asyncpg.Connection, market: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT date, market, regime, index_symbol, index_close, sma_50, sma_200,
               vix, realized_vol, breadth_pct, reason, created_at
        FROM market_regime
        WHERE market = $1
        ORDER BY date DESC
        LIMIT 1
        """,
        market,
    )


async def get_regime_history(conn: asyncpg.Connection, market: str, days: int = 90) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT date, regime, index_close, vix, realized_vol, breadth_pct, reason
        FROM market_regime
        WHERE market = $1 AND date >= CURRENT_DATE - $2::int
        ORDER BY date DESC
        """,
        market, days,
    )
