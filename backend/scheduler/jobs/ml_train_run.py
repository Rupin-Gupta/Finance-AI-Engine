"""Scheduled job: retrain the ML directional model, walk-forward validate, promote on edge (P14).

Builds a cross-symbol dataset from stored analytics + closes + sentiment (labels strictly
forward — see ml/features), sorts it GLOBALLY BY DATE so the walk-forward split trains on
the past and tests on the future across all names (no lookahead), fits a shallow GBM, and
**promotes only if the out-of-sample edge clears the gate**. An unpromoted model is never
used — the ML signal weight is effectively 0 until the model earns it.
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from backend.config import settings
from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.analytics import get_analytics
from backend.db.queries.market_data import get_ohlcv
from backend.db.queries.sentiment import get_sentiment_by_date_range
from backend.db.queries.ml_models import insert_model
from backend.ml.features import build_dataset, FEATURE_NAMES
from backend.ml.model import train_bundle, save_bundle
from backend.scheduler.jobs._base import run_with_retry

logger = logging.getLogger(__name__)

_TRAIN_DAYS = 1095          # up to 3y of history per symbol
_MIN_ROWS_PER_SYMBOL = 60


async def _build_corpus(pool, symbols: list[str]) -> tuple[list, list, list]:
    now = datetime.now(tz=timezone.utc)
    start = now - timedelta(days=_TRAIN_DAYS)
    X_all, y_all, d_all = [], [], []
    for sym in symbols:
        try:
            async with pool.acquire() as conn:
                arows = await get_analytics(conn, sym, start, now)
                if len(arows) < _MIN_ROWS_PER_SYMBOL:
                    continue
                orows = await get_ohlcv(conn, sym, start, now)
                closes = {r["timestamp"].date(): float(r["close"])
                          for r in orows if r["close"] is not None}
                sent = await get_sentiment_by_date_range(conn, sym, start.date(), now.date())
            X, y, dates = build_dataset(
                [dict(r) for r in arows], closes, sent,
                horizon=settings.ml_horizon_days, threshold=settings.ml_threshold,
            )
            X_all.extend(X)
            y_all.extend(y)
            d_all.extend(dates)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ml_train_run: %s skipped: %s", sym, exc)
    # GLOBAL time-sort so walk-forward folds are strictly past→future across symbols.
    order = sorted(range(len(d_all)), key=lambda i: d_all[i])
    return ([X_all[i] for i in order], [y_all[i] for i in order], [d_all[i] for i in order])


async def _run() -> None:
    pool = get_db_pool()
    symbols = [s.strip() for s in settings.tracked_symbols.split(",") if s.strip()]
    if settings.ml_max_symbols > 0:
        symbols = symbols[: settings.ml_max_symbols]

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "ml_train_run")

    try:
        X, y, _ = await _build_corpus(pool, symbols)
        if len(y) < 500:
            async with pool.acquire() as conn:
                await update_job_status(conn, job_id, "completed")
            logger.warning("ml_train_run: only %d samples — skipping training", len(y))
            return

        bundle = train_bundle(X, y, FEATURE_NAMES,
                              settings.ml_horizon_days, settings.ml_threshold)
        promoted = bundle.metrics.passes_gate()

        version = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
        os.makedirs(settings.ml_model_dir, exist_ok=True)
        path = os.path.join(settings.ml_model_dir, f"ml_{version}.joblib")
        save_bundle(bundle, path)

        m = bundle.metrics
        async with pool.acquire() as conn:
            await insert_model(conn, {
                "version": version, "horizon": settings.ml_horizon_days,
                "threshold": settings.ml_threshold, "n_samples": m.n_samples,
                "n_features": m.n_features, "oos_auc": m.oos_auc,
                "oos_hit_rate": m.oos_hit_rate, "oos_brier": m.oos_brier,
                "promoted": promoted, "path": path, "feature_names": FEATURE_NAMES,
            })
            await update_job_status(conn, job_id, "completed")
        logger.info("ml_train_run: v%s samples=%d auc=%s hit=%s brier=%s promoted=%s",
                    version, m.n_samples, m.oos_auc, m.oos_hit_rate, m.oos_brier, promoted)
    except Exception as exc:
        async with pool.acquire() as conn:
            await update_job_status(conn, job_id, "failed", str(exc))
        raise


async def run() -> None:
    await run_with_retry(_run, "ml_train_run")
