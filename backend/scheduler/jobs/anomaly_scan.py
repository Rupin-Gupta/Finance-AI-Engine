import pandas as pd
from datetime import datetime, timedelta, timezone

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.market_data import get_ohlcv
from backend.db.queries.alerts import insert_alert
from backend.db.queries.jobs import create_job, update_job_status
from backend.analytics.anomaly import zscore_anomalies, rolling_threshold_anomalies

ZSCORE_THRESHOLD = 3.0
VOLUME_SIGMA = 2.5


async def run() -> None:
    pool = get_db_pool()
    symbols = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]
    async with pool.acquire() as conn:
        job_id = await create_job(conn, "anomaly_scan")
        try:
            end = datetime.now(tz=timezone.utc)
            start = end - timedelta(days=60)
            for symbol in symbols:
                rows = await get_ohlcv(conn, symbol, start, end)
                if not rows:
                    continue
                df = pd.DataFrame([dict(r) for r in rows])
                # asyncpg returns NUMERIC as Decimal — coerce before float math
                for col in ("open", "high", "low", "close", "volume"):
                    if col in df.columns:
                        df[col] = df[col].astype(float)
                price_anomalies = zscore_anomalies(df, col="close", threshold=ZSCORE_THRESHOLD)
                for _, row in price_anomalies.iterrows():
                    await insert_alert(conn, symbol, "price_zscore", row["close"], ZSCORE_THRESHOLD)
                vol_anomalies = rolling_threshold_anomalies(df, col="volume", sigma=VOLUME_SIGMA)
                for _, row in vol_anomalies.iterrows():
                    await insert_alert(conn, symbol, "volume_spike", row["volume"], VOLUME_SIGMA)
            await update_job_status(conn, job_id, "completed")
        except Exception as exc:
            await update_job_status(conn, job_id, "failed", error=str(exc))
            raise
