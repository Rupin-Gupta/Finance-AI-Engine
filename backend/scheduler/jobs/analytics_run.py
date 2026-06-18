import pandas as pd
from datetime import datetime, timedelta, timezone

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.market_data import get_ohlcv
from backend.db.queries.analytics import upsert_analytics
from backend.db.queries.jobs import create_job, update_job_status
from backend.analytics.indicators import add_all_indicators


async def run() -> None:
    pool = get_db_pool()
    symbols = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]
    async with pool.acquire() as conn:
        job_id = await create_job(conn, "analytics_run")
        try:
            end = datetime.now(tz=timezone.utc)
            start = end - timedelta(days=60)
            for symbol in symbols:
                rows = await get_ohlcv(conn, symbol, start, end)
                if not rows:
                    continue
                df = pd.DataFrame([dict(r) for r in rows]).sort_values("timestamp")
                # asyncpg returns NUMERIC as Decimal — coerce before float math
                for col in ("open", "high", "low", "close", "volume"):
                    if col in df.columns:
                        df[col] = df[col].astype(float)
                df = add_all_indicators(df)
                analytics_rows = df[
                    ["symbol", "timestamp", "sma_20", "ema_9", "ema_20", "rsi_14", "volatility_20", "momentum_10"]
                ].to_dict("records")
                await upsert_analytics(conn, analytics_rows)
            await update_job_status(conn, job_id, "completed")
        except Exception as exc:
            await update_job_status(conn, job_id, "failed", error=str(exc))
            raise
