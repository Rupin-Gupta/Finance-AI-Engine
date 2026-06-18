"""Scheduled job: snapshot per-signal accuracy + return attribution → signal_performance.

Builds the R3 history/trend so signal edge (and its decay) can be tracked over time.
"""
import logging
from datetime import datetime, timedelta, timezone

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.decisions import get_decisions_with_signals_since
from backend.db.queries.market_data import get_closes_by_symbol
from backend.db.queries.signal_performance import upsert_snapshot
from backend.db.queries.calibration_summary import upsert_calibration_summary
from backend.db.queries.alerts import insert_alert
from backend.analytics.calibration import (
    score_for_calibration, signal_contribution, calibration_summary,
)
from backend.analytics.drift import drift_verdict, VERDICT_DEGRADING, VERDICT_RETRAIN
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)

_HORIZON_DAYS = 5
_LOOKBACK_DAYS = 180


async def _run() -> None:
    pool = get_db_pool()
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=_LOOKBACK_DAYS)

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "signal_snapshot_run")

    try:
        async with pool.acquire() as conn:
            decisions = await get_decisions_with_signals_since(conn, start)
            symbols = sorted({d["symbol"] for d in decisions})
            closes = await get_closes_by_symbol(conn, symbols, start - timedelta(days=10), now)

            scored = score_for_calibration(decisions, closes, _HORIZON_DAYS, now.date())
            signals = signal_contribution(scored)
            count = await upsert_snapshot(conn, now.date(), _HORIZON_DAYS, _LOOKBACK_DAYS, signals)
            # R2.1: persist the calibration read-cache so the decision endpoint can map
            # confidence → calibrated win probability with a single cheap row read.
            await upsert_calibration_summary(conn, _HORIZON_DAYS, calibration_summary(scored))

            # R7: drift check — recent hit rate vs baseline; alert on decay so the
            # dashboard's alert feed (and future P4 notifications) surface it.
            drift = drift_verdict(scored)
            if drift["status"] in (VERDICT_DEGRADING, VERDICT_RETRAIN):
                await insert_alert(conn, "MODEL", f"model_drift_{drift['status']}",
                                   value=drift["delta"], threshold=-0.05)
                logger.warning("signal_snapshot_run: model drift %s (delta %.3f)",
                               drift["status"], drift["delta"])

        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "completed")
        logger.info("signal_snapshot_run: snapshotted %d signals from %d decisions", count, len(scored))
    except Exception as exc:
        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "failed", str(exc))
        raise


async def run() -> None:
    await run_with_retry(_run, "signal_snapshot_run")
