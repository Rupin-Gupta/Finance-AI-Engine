"""Scheduled job: auto-execute paper trades from the latest decisions + snapshot equity.

Closes R1.1 (auto-exec each cycle) + R2.3 (size = recommended_pct × equity). The trade
universe is bounded to the watchlist ∪ current paper positions, so it never tries to trade
all 700+ tracked symbols. Sizing reuses the position-sizing engine with the calibrated
win probability (R2.1). Equity is snapshotted every run (R1.2) regardless of whether
auto-trading is enabled, so the equity curve keeps building.

Auto-trading is OFF unless `PAPER_AUTO_TRADE_ENABLED=true` — it moves the (virtual) book
unattended, so it is opt-in.
"""
import logging
from datetime import datetime, timezone

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.paper import (
    get_or_create_portfolio, get_positions, update_cash, upsert_position,
    delete_position, insert_trade, insert_equity_snapshot,
)
from backend.db.queries.market_data import get_latest_prices
from backend.db.queries.decisions import get_latest_decisions_multi
from backend.db.queries.watchlist import list_watchlist
from backend.db.queries.calibration_summary import get_calibration_summary
from backend.analytics.backtest import CostModel
from backend.analytics.sizing import recommend_size
from backend.analytics.calibration import lookup_calibrated_prob
from backend.analytics.paper_trading import execute_trade, portfolio_metrics, plan_rebalance
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)


def _positions_dict(rows) -> dict:
    return {r["symbol"]: {"quantity": float(r["quantity"]), "avg_cost": float(r["avg_cost"])}
            for r in rows}


def _win_prob(calibration: dict | None, confidence) -> float | None:
    if not calibration:
        return None
    bins = (calibration.get("reliability") or {}).get("bins") or []
    return lookup_calibrated_prob(bins, confidence, fallback=confidence)


async def _run() -> None:
    pool = get_db_pool()
    now = datetime.now(tz=timezone.utc)

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "paper_auto_run")

    try:
        async with pool.acquire() as conn:
            pf = await get_or_create_portfolio(conn, settings.paper_starting_cash)
            cash = float(pf["cash"])
            starting = float(pf["starting_cash"])
            positions = _positions_dict(await get_positions(conn))
            wl = await list_watchlist(conn)

            universe = sorted(set(positions) | {r["symbol"] for r in wl})
            prices = await get_latest_prices(conn, universe) if universe else {}

            # Equity BEFORE trading drives the sizing target (fixed base avoids drift).
            equity = portfolio_metrics(cash, positions, prices, starting)["equity"]

            executed = 0
            if settings.paper_auto_trade_enabled and universe:
                decisions = await get_latest_decisions_multi(conn, universe)
                calibration = await get_calibration_summary(conn, horizon_days=5)

                for sym in universe:
                    dec = decisions.get(sym)
                    price = prices.get(sym)
                    if not dec or price is None:
                        continue
                    conf = float(dec["confidence"]) if dec["confidence"] is not None else None
                    sizing = recommend_size(conf, None, dec["risk_level"],
                                            win_prob=_win_prob(calibration, conf))
                    current_qty = positions.get(sym, {}).get("quantity", 0.0)
                    order = plan_rebalance(dec["recommendation"], sizing["recommended_pct"],
                                           equity, price, current_qty)
                    if not order:
                        continue
                    try:
                        cash, positions, trade = execute_trade(
                            cash, positions, order["side"], sym, order["quantity"], price,
                            cost_model=CostModel.for_symbol(sym),
                        )
                    except ValueError as exc:
                        logger.info("paper_auto_run: skip %s — %s", sym, exc)
                        continue
                    async with conn.transaction():
                        await update_cash(conn, cash)
                        new_pos = positions.get(sym)
                        if new_pos:
                            await upsert_position(conn, sym, new_pos["quantity"], new_pos["avg_cost"])
                        else:
                            await delete_position(conn, sym)
                        await insert_trade(conn, trade)
                    executed += 1

            # Always snapshot the (post-trade) equity curve point.
            metrics = portfolio_metrics(cash, positions, prices, starting)
            await insert_equity_snapshot(conn, metrics)

        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "completed")
        logger.info("paper_auto_run: executed=%d, equity=%.2f, auto=%s",
                    executed, metrics["equity"], settings.paper_auto_trade_enabled)
    except Exception as exc:
        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "failed", str(exc))
        raise


async def run() -> None:
    await run_with_retry(_run, "paper_auto_run")
