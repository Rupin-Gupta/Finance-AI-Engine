import asyncpg
from datetime import datetime


async def upsert_analytics(conn: asyncpg.Connection, rows: list[dict]) -> int:
    """Upsert analytics rows on (symbol, timestamp). NaN → NULL via None."""
    stmt = """
        INSERT INTO analytics (symbol, timestamp, sma_20, ema_20, rsi_14, volatility_20, momentum_10)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (symbol, timestamp) DO UPDATE SET
            sma_20        = EXCLUDED.sma_20,
            ema_20        = EXCLUDED.ema_20,
            rsi_14        = EXCLUDED.rsi_14,
            volatility_20 = EXCLUDED.volatility_20,
            momentum_10   = EXCLUDED.momentum_10,
            computed_at   = now()
    """
    import math

    def _coerce(v):
        if v is None:
            return None
        try:
            return None if math.isnan(float(v)) else float(v)
        except (TypeError, ValueError):
            return None

    data = [
        (
            r["symbol"],
            r["timestamp"],
            _coerce(r.get("sma_20")),
            _coerce(r.get("ema_20")),
            _coerce(r.get("rsi_14")),
            _coerce(r.get("volatility_20")),
            _coerce(r.get("momentum_10")),
        )
        for r in rows
    ]
    await conn.executemany(stmt, data)
    return len(data)


async def get_analytics(
    conn: asyncpg.Connection, symbol: str, start: datetime, end: datetime
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT symbol, timestamp, sma_20, ema_20, rsi_14, volatility_20, momentum_10
        FROM analytics
        WHERE symbol = $1 AND timestamp BETWEEN $2 AND $3
        ORDER BY timestamp
        """,
        symbol, start, end,
    )
