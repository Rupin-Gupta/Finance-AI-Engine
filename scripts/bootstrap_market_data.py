"""One-off bootstrap: ingest 1y OHLCV for every tracked symbol, then recompute analytics.

Per-symbol resilient (a delisted/renamed ticker never aborts the rest), progress-logged,
job-tracked. Run from the host against the compose DB:

    DATABASE_URL=postgresql://postgres:<pw>@localhost:5432/finance \
        .venv/bin/python scripts/bootstrap_market_data.py
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from backend.data.symbols import ALL_SYMBOLS
from backend.db.connection import init_db_pool, get_db_pool, close_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.db.queries.stocks import ensure_stocks
from backend.db.queries.market_data import get_ohlcv, upsert_market_data
from backend.db.queries.analytics import upsert_analytics
from backend.ingest.market import fetch_ohlcv
from backend.analytics.indicators import add_all_indicators

PERIOD = "1y"
INTERVAL = "1d"


async def _ingest(conn, symbols: list[str]) -> tuple[int, list[str]]:
    ok, failed = 0, []
    for i, sym in enumerate(symbols, 1):
        try:
            rows = await fetch_ohlcv(sym, period=PERIOD, interval=INTERVAL)
            rows = [r for r in rows if all(r.get(f) is not None for f in ("symbol", "timestamp", "close"))]
            if rows:
                await upsert_market_data(conn, rows)
                ok += 1
            else:
                failed.append(sym)
        except Exception as exc:
            failed.append(sym)
            print(f"  FAIL {sym}: {exc}", flush=True)
        if i % 25 == 0:
            print(f"progress: {i}/{len(symbols)} ({ok} ok, {len(failed)} failed)", flush=True)
    return ok, failed


async def _recompute_analytics(conn) -> int:
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=3650)
    symbols = [r["symbol"] for r in await conn.fetch("SELECT DISTINCT symbol FROM market_data")]
    total = 0
    for sym in symbols:
        rows = await get_ohlcv(conn, sym, start, end)
        if len(rows) < 2:
            continue
        df = pd.DataFrame([dict(r) for r in rows]).sort_values("timestamp")
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = df[col].astype(float)
        df = add_all_indicators(df)
        recs = df[["symbol", "timestamp", "sma_20", "ema_9", "ema_20", "rsi_14",
                   "volatility_20", "momentum_10"]].to_dict("records")
        total += await upsert_analytics(conn, recs)
    return total


async def main() -> None:
    await init_db_pool()
    pool = get_db_pool()
    symbols = list(ALL_SYMBOLS)
    print(f"bootstrap: {len(symbols)} symbols, period={PERIOD}", flush=True)

    async with pool.acquire() as conn:
        job_id = await create_job(conn, "market_bootstrap")
        try:
            await ensure_stocks(conn, symbols)
            ok, failed = await _ingest(conn, symbols)
            print(f"ingest done: {ok} ok, {len(failed)} failed: {failed[:20]}", flush=True)
            rows = await _recompute_analytics(conn)
            print(f"analytics recomputed: {rows} rows", flush=True)
            status = "completed" if ok else "failed"
            err = f"{len(failed)} symbols failed: {failed[:50]}" if failed else None
            await update_job_status(conn, job_id, status, error=err)
        except Exception as exc:
            await update_job_status(conn, job_id, "failed", error=str(exc))
            raise
    await close_db_pool()
    print("bootstrap complete", flush=True)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
