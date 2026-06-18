"""Signal performance snapshots (R3 history) — query helpers."""
from datetime import date

import pytest

from backend.db.queries import signal_performance as sp_q


class FakeConn:
    def __init__(self, fetch=None):
        self._fetch = fetch or []
        self.executed = []

    async def executemany(self, q, data):
        self.executed.append((q, data))

    async def fetch(self, q, *args):
        self.executed.append((q, args))
        return self._fetch


@pytest.mark.asyncio
async def test_upsert_snapshot_counts_and_skips_empty():
    conn = FakeConn()
    n = await sp_q.upsert_snapshot(conn, date(2026, 6, 1), 5, 180, [
        {"signal": "rsi", "active_count": 10, "accuracy": 0.6,
         "attributed_return": 0.03, "avg_weight": 0.12},
    ])
    assert n == 1
    assert conn.executed  # executemany called
    assert await sp_q.upsert_snapshot(conn, date(2026, 6, 1), 5, 180, []) == 0


@pytest.mark.asyncio
async def test_get_signal_history_returns_rows():
    rows = [{"snapshot_date": date(2026, 6, 1), "signal": "rsi", "active_count": 10,
             "accuracy": 0.6, "attributed_return": 0.03, "avg_weight": 0.12}]
    out = await sp_q.get_signal_history(FakeConn(fetch=rows), "rsi", 180)
    assert out == rows
