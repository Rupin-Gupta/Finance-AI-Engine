import asyncpg
import json


async def upsert_decision(conn: asyncpg.Connection, row: dict) -> None:
    await conn.execute(
        """
        INSERT INTO decisions (symbol, recommendation, confidence, signals_json, risk_level,
                               explanation, bull_case, bear_case)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        row["symbol"],
        row["recommendation"],
        float(row["confidence"]),
        json.dumps(row["signals_json"]),
        row["risk_level"],
        row.get("explanation", ""),
        row.get("bull_case", ""),
        row.get("bear_case", ""),
    )


async def get_latest_decision(conn: asyncpg.Connection, symbol: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT * FROM decisions
        WHERE symbol=$1
        ORDER BY created_at DESC
        LIMIT 1
        """,
        symbol,
    )


async def get_decisions_since(
    conn: asyncpg.Connection, start, symbol: str | None = None
) -> list[asyncpg.Record]:
    """Decisions created on/after `start`, oldest first. Optionally filtered to one symbol.
    Used by the accuracy tracker to score past calls against realized prices."""
    if symbol:
        return await conn.fetch(
            """
            SELECT symbol, recommendation, confidence, risk_level, created_at
            FROM decisions
            WHERE created_at >= $1 AND symbol = $2
            ORDER BY created_at
            """,
            start, symbol,
        )
    return await conn.fetch(
        """
        SELECT symbol, recommendation, confidence, risk_level, created_at
        FROM decisions
        WHERE created_at >= $1
        ORDER BY created_at
        """,
        start,
    )


async def get_decisions_with_signals_since(
    conn: asyncpg.Connection, start, symbol: str | None = None
) -> list[asyncpg.Record]:
    """Like get_decisions_since but also returns signals_json — for calibration analysis."""
    if symbol:
        return await conn.fetch(
            """
            SELECT symbol, recommendation, confidence, risk_level, signals_json, created_at
            FROM decisions
            WHERE created_at >= $1 AND symbol = $2
            ORDER BY created_at
            """,
            start, symbol,
        )
    return await conn.fetch(
        """
        SELECT symbol, recommendation, confidence, risk_level, signals_json, created_at
        FROM decisions
        WHERE created_at >= $1
        ORDER BY created_at
        """,
        start,
    )


async def get_latest_decisions_multi(
    conn: asyncpg.Connection, symbols: list[str]
) -> dict[str, asyncpg.Record]:
    """Return {symbol: most-recent decision row} for the given symbols (one query)."""
    if not symbols:
        return {}
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (symbol)
            symbol, recommendation, confidence, risk_level, created_at
        FROM decisions
        WHERE symbol = ANY($1)
        ORDER BY symbol, created_at DESC
        """,
        symbols,
    )
    return {r["symbol"]: r for r in rows}


async def upsert_forecasts(conn: asyncpg.Connection, rows: list[dict]) -> int:
    stmt = """
        INSERT INTO forecasts (symbol, forecast_date, predicted_close, lower_bound, upper_bound)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (symbol, forecast_date) DO UPDATE SET
            predicted_close = EXCLUDED.predicted_close,
            lower_bound     = EXCLUDED.lower_bound,
            upper_bound     = EXCLUDED.upper_bound,
            created_at      = now()
    """
    data = [
        (
            r["symbol"],
            r["forecast_date"],
            float(r["predicted_close"]),
            float(r["lower_bound"]),
            float(r["upper_bound"]),
        )
        for r in rows
    ]
    await conn.executemany(stmt, data)
    return len(data)


async def get_forecasts(conn: asyncpg.Connection, symbol: str, days: int = 7) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT forecast_date, predicted_close, lower_bound, upper_bound
        FROM forecasts
        WHERE symbol=$1 AND forecast_date >= CURRENT_DATE
        ORDER BY forecast_date ASC
        LIMIT $2
        """,
        symbol, days,
    )


async def set_decision_committee(conn: asyncpg.Connection, symbol: str, committee: dict) -> bool:
    """Attach the committee verdict (R10) to the symbol's latest decision row."""
    result = await conn.execute(
        """
        UPDATE decisions SET committee_json = $2
        WHERE id = (SELECT id FROM decisions WHERE symbol = $1 ORDER BY created_at DESC LIMIT 1)
        """,
        symbol, json.dumps(committee),
    )
    return result.rsplit(" ", 1)[-1] != "0"
