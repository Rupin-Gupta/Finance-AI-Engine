import asyncpg


async def upsert_snapshot(
    conn: asyncpg.Connection, snapshot_date, horizon_days: int, lookback_days: int,
    signals: list[dict],
) -> int:
    """Persist one day's per-signal stats (from calibration.signal_contribution)."""
    if not signals:
        return 0
    stmt = """
        INSERT INTO signal_performance
            (snapshot_date, signal, horizon_days, lookback_days, active_count,
             accuracy, attributed_return, avg_weight)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (snapshot_date, signal, horizon_days) DO UPDATE SET
            lookback_days     = EXCLUDED.lookback_days,
            active_count      = EXCLUDED.active_count,
            accuracy          = EXCLUDED.accuracy,
            attributed_return = EXCLUDED.attributed_return,
            avg_weight        = EXCLUDED.avg_weight,
            created_at        = now()
    """
    data = [
        (snapshot_date, s["signal"], horizon_days, lookback_days, s["active_count"],
         s.get("accuracy"), s.get("attributed_return"), s.get("avg_weight"))
        for s in signals
    ]
    await conn.executemany(stmt, data)
    return len(data)


async def get_signal_history(
    conn: asyncpg.Connection, signal: str | None = None, days: int = 180
) -> list[asyncpg.Record]:
    """Per-signal snapshots over the last `days`, oldest first (for trend charts)."""
    if signal:
        return await conn.fetch(
            """
            SELECT snapshot_date, signal, active_count, accuracy, attributed_return, avg_weight
            FROM signal_performance
            WHERE signal = $1 AND snapshot_date >= CURRENT_DATE - $2::int
            ORDER BY snapshot_date
            """,
            signal, days,
        )
    return await conn.fetch(
        """
        SELECT snapshot_date, signal, active_count, accuracy, attributed_return, avg_weight
        FROM signal_performance
        WHERE snapshot_date >= CURRENT_DATE - $1::int
        ORDER BY snapshot_date, signal
        """,
        days,
    )


async def get_signal_rollup(
    conn: asyncpg.Connection, days: int = 365
) -> list[asyncpg.Record]:
    """Trailing-window per-signal rollup (R3.1): mean accuracy + total/mean attribution
    across all snapshots in the window. Defaults to trailing 12 months."""
    return await conn.fetch(
        """
        SELECT signal,
               COUNT(*)                   AS snapshots,
               AVG(accuracy)              AS avg_accuracy,
               SUM(attributed_return)     AS total_attributed_return,
               AVG(attributed_return)     AS avg_attributed_return,
               AVG(avg_weight)            AS avg_weight,
               SUM(active_count)          AS total_active
        FROM signal_performance
        WHERE snapshot_date >= CURRENT_DATE - $1::int
        GROUP BY signal
        ORDER BY total_attributed_return DESC NULLS LAST
        """,
        days,
    )
