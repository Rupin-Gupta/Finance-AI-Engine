import asyncpg
import json


async def upsert_decision(conn: asyncpg.Connection, row: dict) -> None:
    await conn.execute(
        """
        INSERT INTO decisions (symbol, recommendation, confidence, signals_json, risk_level, explanation)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        row["symbol"],
        row["recommendation"],
        float(row["confidence"]),
        json.dumps(row["signals_json"]),
        row["risk_level"],
        row.get("explanation", ""),
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
