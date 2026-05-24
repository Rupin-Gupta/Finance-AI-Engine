import os
import pandas as pd
from datetime import datetime, timedelta

from backend.db.connection import get_db_pool
from backend.db.queries.market_data import get_ohlcv
from backend.db.queries.alerts import insert_alert
from backend.db.queries.jobs import create_job, update_job_status
from backend.analytics.anomaly import zscore_anomalies, rolling_threshold_anomalies

SYMBOLS = os.getenv("TRACKED_SYMBOLS", "AAPL,MSFT,GOOGL,AMZN,TSLA").split(",")
ZSCORE_THRESHOLD = 3.0
VOLUME_SIGMA = 2.5


async def run() -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        job_id = await create_job(conn, "anomaly_scan")
        try:
            end = datetime.utcnow()
            start = end - timedelta(days=60)
            for symbol in SYMBOLS:
                rows = await get_ohlcv(conn, symbol, start, end)
                if not rows:
                    continue
                df = pd.DataFrame([dict(r) for r in rows])
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
