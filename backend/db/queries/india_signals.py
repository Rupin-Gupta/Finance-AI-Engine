"""India market signals (P5) — persistence."""
import asyncpg


async def upsert_market_signals(conn: asyncpg.Connection, row: dict) -> None:
    await conn.execute(
        """
        INSERT INTO india_market_signals
            (date, fii_net_cr, dii_net_cr, pcr, gift_nifty_pct, gift_nifty_level, source)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (date) DO UPDATE SET
            fii_net_cr       = COALESCE(EXCLUDED.fii_net_cr, india_market_signals.fii_net_cr),
            dii_net_cr       = COALESCE(EXCLUDED.dii_net_cr, india_market_signals.dii_net_cr),
            pcr              = COALESCE(EXCLUDED.pcr, india_market_signals.pcr),
            gift_nifty_pct   = COALESCE(EXCLUDED.gift_nifty_pct, india_market_signals.gift_nifty_pct),
            gift_nifty_level = COALESCE(EXCLUDED.gift_nifty_level, india_market_signals.gift_nifty_level),
            source           = EXCLUDED.source,
            created_at       = now()
        """,
        row["date"], row.get("fii_net_cr"), row.get("dii_net_cr"), row.get("pcr"),
        row.get("gift_nifty_pct"), row.get("gift_nifty_level"), row.get("source"),
    )


async def get_latest_market_signals(conn: asyncpg.Connection) -> asyncpg.Record | None:
    return await conn.fetchrow(
        "SELECT * FROM india_market_signals ORDER BY date DESC LIMIT 1"
    )


def market_context(row: asyncpg.Record | None) -> dict | None:
    """Shape a DB row into the dict score_india_market expects (or None)."""
    if not row:
        return None
    def _f(v):
        return float(v) if v is not None else None
    return {
        "fii_net_cr": _f(row["fii_net_cr"]),
        "dii_net_cr": _f(row["dii_net_cr"]),
        "pcr": _f(row["pcr"]),
        "gift_nifty_pct": _f(row["gift_nifty_pct"]),
    }


async def upsert_bulk_deals(conn: asyncpg.Connection, deals: list[dict]) -> int:
    if not deals:
        return 0
    stmt = """
        INSERT INTO bulk_block_deals
            (deal_date, symbol, client, side, quantity, price, deal_type)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (deal_date, symbol, client, side, quantity, deal_type) DO NOTHING
    """
    data = [
        (d["deal_date"], d["symbol"], d.get("client"), d.get("side"),
         d.get("quantity"), d.get("price"), d.get("deal_type"))
        for d in deals
    ]
    await conn.executemany(stmt, data)
    return len(data)


async def get_bulk_deals(
    conn: asyncpg.Connection, symbol: str, limit: int = 20
) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT deal_date, symbol, client, side, quantity, price, deal_type
        FROM bulk_block_deals WHERE symbol = $1 ORDER BY deal_date DESC LIMIT $2
        """,
        symbol, limit,
    )
