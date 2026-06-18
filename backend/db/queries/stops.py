"""position_stops config table access (P3)."""
import asyncpg


async def get_stop_configs(conn: asyncpg.Connection, symbols: list[str] | None = None) -> dict[str, dict]:
    """{symbol: {stop_pct, trailing}} for configured symbols (all if symbols None)."""
    if symbols is not None and not symbols:
        return {}
    if symbols is None:
        rows = await conn.fetch("SELECT symbol, stop_pct, is_trailing FROM position_stops")
    else:
        rows = await conn.fetch(
            "SELECT symbol, stop_pct, is_trailing FROM position_stops WHERE symbol = ANY($1::text[])",
            symbols,
        )
    return {
        r["symbol"]: {"stop_pct": float(r["stop_pct"]) if r["stop_pct"] is not None else None,
                      "trailing": r["is_trailing"]}
        for r in rows
    }


async def upsert_stop_config(conn: asyncpg.Connection, symbol: str,
                             stop_pct: float | None, trailing: bool) -> None:
    await conn.execute(
        """
        INSERT INTO position_stops (symbol, stop_pct, is_trailing)
        VALUES ($1, $2, $3)
        ON CONFLICT (symbol) DO UPDATE SET
            stop_pct = EXCLUDED.stop_pct,
            is_trailing = EXCLUDED.is_trailing,
            updated_at = now()
        """,
        symbol, stop_pct, trailing,
    )
