"""Scheduled job: check stop-loss breaches on held positions → alerts (P3).

Daily. Evaluates trailing/fixed stops for watchlist holdings and the paper book; a
breach writes a `stop_breach` alert (reuses the alerts table, like R7 drift) so the
dashboard feed — and future P4 notifications — surface "X broke its stop". Makes stops
active, not just a viewer.
"""
import logging

from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.watchlist import list_watchlist
from backend.db.queries.paper import get_positions
from backend.db.queries.market_data import get_latest_prices, get_high_water, get_latest_volatility
from backend.db.queries.decisions import get_latest_decisions_multi
from backend.db.queries.stops import get_stop_configs
from backend.db.queries.alerts import insert_alert
from backend.analytics.stops import position_stop
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 90


async def _check_source(conn, holdings: list[tuple[str, float]]) -> int:
    symbols = [s for s, _ in holdings]
    if not symbols:
        return 0
    prices = await get_latest_prices(conn, symbols)
    highs = await get_high_water(conn, symbols, days=_LOOKBACK_DAYS)
    vols = await get_latest_volatility(conn, symbols)
    decisions = await get_latest_decisions_multi(conn, symbols)
    configs = await get_stop_configs(conn, symbols)

    breaches = 0
    for sym, entry in holdings:
        cfg = configs.get(sym, {})
        dec = decisions.get(sym)
        stop = position_stop(
            entry=entry, current=prices.get(sym), high_water=highs.get(sym),
            vol_20=vols.get(sym), risk_level=dec["risk_level"] if dec else None,
            stop_pct=cfg.get("stop_pct"), trailing=cfg.get("trailing", True),
        )
        if stop and stop["breached"]:
            await insert_alert(conn, sym, "stop_breach", stop["current"], stop["stop_level"])
            breaches += 1
    return breaches


async def _run() -> None:
    pool = get_db_pool()
    async with pool.acquire() as conn:
        job_id = await create_job(conn, "stops_run")
        try:
            wl = await list_watchlist(conn)
            paper = await get_positions(conn)
            total = await _check_source(conn, [(r["symbol"], float(r["cost_basis"]))
                                               for r in wl if r["cost_basis"]])
            total += await _check_source(conn, [(r["symbol"], float(r["avg_cost"]))
                                                for r in paper if r["avg_cost"]])
            await update_job_status(conn, job_id, "completed")
            logger.info("stops_run: %d stop breaches alerted", total)
        except Exception as exc:
            await update_job_status(conn, job_id, "failed", str(exc))
            raise


async def run() -> None:
    await run_with_retry(_run, "stops_run")
