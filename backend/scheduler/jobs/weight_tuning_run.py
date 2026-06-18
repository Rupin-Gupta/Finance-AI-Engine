"""Scheduled job: optimize the 8 signal weights → signal_weights table.

R4 upgrades:
  - net-of-cost objective: weights are scored on return AFTER round-trip costs.
  - attribution prior: the search is seeded around the R3 signal-attribution vector.
  - expanding-window CV: validation across several sequential folds, not one split.

Auto-promotes the new weight set only if it beats the current weights OUT-OF-SAMPLE
(mean improvement across folds). The decision engine then reads the promoted set.
"""
import logging
from datetime import datetime, timedelta, timezone

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.decisions import get_decisions_with_signals_since
from backend.db.queries.market_data import get_closes_by_symbol
from backend.db.queries.signal_weights import insert_weight_set
from backend.analytics.calibration import score_for_calibration, signal_contribution
from backend.analytics.weight_tuning import walk_forward_expanding, attribution_prior
from backend.decision.engine import BUY_THRESHOLD
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)

_HORIZON_DAYS = 5
_LOOKBACK_DAYS = 365


async def _run() -> None:
    pool = get_db_pool()
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=_LOOKBACK_DAYS)

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "weight_tuning_run")

    try:
        async with pool.acquire() as conn:
            decisions = await get_decisions_with_signals_since(conn, start)
            symbols = sorted({d["symbol"] for d in decisions})
            closes = await get_closes_by_symbol(conn, symbols, start - timedelta(days=10), now)
            scored = score_for_calibration(decisions, closes, _HORIZON_DAYS, now.date())

            # R3→R4: seed the search with the measured per-signal return attribution.
            prior = attribution_prior(signal_contribution(scored))
            # R4.1/R4.2: net-of-cost objective, validated with expanding-window CV.
            result = walk_forward_expanding(
                scored, BUY_THRESHOLD, prior=prior, use_costs=True, objective="net_return",
            )
            promotable = bool(result.get("promotable"))
            await insert_weight_set(conn, result, promoted=promotable)

        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "completed")
        logger.info("weight_tuning_run: %d scored, method=%s, improvement=%s, promoted=%s",
                    len(scored), result.get("method"), result.get("improvement"), promotable)
    except Exception as exc:
        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "failed", str(exc))
        raise


async def run() -> None:
    await run_with_retry(_run, "weight_tuning_run")
