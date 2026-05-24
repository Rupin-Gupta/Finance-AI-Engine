"""Prophet 7-day price forecasting."""
import asyncio
import logging
from datetime import date, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

_PROPHET_TIMEOUT_SECONDS = 60


def _run_prophet(ohlcv_rows: list[dict], horizon_days: int = 7) -> list[dict]:
    """CPU-bound: train Prophet and return forecast rows."""
    from prophet import Prophet

    df = pd.DataFrame(ohlcv_rows)[["timestamp", "close"]].dropna()
    df = df.rename(columns={"timestamp": "ds", "close": "y"})
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)
    df = df.sort_values("ds").drop_duplicates("ds")

    if len(df) < 10:
        logger.warning("Prophet skipped: only %d rows (need ≥10)", len(df))
        return []

    try:
        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=True,
            interval_width=0.80,
        )
        model.fit(df)
    except Exception as exc:
        logger.error("Prophet model.fit() failed: %s", exc)
        return []

    future = model.make_future_dataframe(periods=horizon_days)
    forecast = model.predict(future)
    forecast = forecast[forecast["ds"] > df["ds"].max()].head(horizon_days)

    return [
        {
            "forecast_date": row["ds"].date(),
            "predicted_close": round(float(row["yhat"]), 4),
            "lower_bound": round(float(row["yhat_lower"]), 4),
            "upper_bound": round(float(row["yhat_upper"]), 4),
        }
        for _, row in forecast.iterrows()
    ]


async def run_forecast(symbol: str, ohlcv_rows: list[dict], horizon_days: int = 7) -> list[dict]:
    """Return forecast rows with symbol injected, ready for db upsert."""
    try:
        rows = await asyncio.wait_for(
            asyncio.to_thread(_run_prophet, ohlcv_rows, horizon_days),
            timeout=_PROPHET_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error("Prophet timed out after %ds for symbol %s", _PROPHET_TIMEOUT_SECONDS, symbol)
        return []
    for r in rows:
        r["symbol"] = symbol
    return rows
