"""Corporate actions: split back-adjustment math + DB query helpers."""
from datetime import date

import pytest

from backend.analytics.corporate_actions import (
    split_adjustment_divisor, apply_split_adjustment,
)
from backend.db.queries import corporate_actions as ca_q


# ---------------------------------------------------------------------------
# split adjustment (pure)
# ---------------------------------------------------------------------------

def test_divisor_only_counts_later_splits():
    splits = [(date(2026, 1, 10), 2.0)]
    assert split_adjustment_divisor(date(2026, 1, 5), splits) == 2.0   # before split → divided
    assert split_adjustment_divisor(date(2026, 1, 10), splits) == 1.0  # on split day → unchanged
    assert split_adjustment_divisor(date(2026, 1, 15), splits) == 1.0  # after → unchanged


def test_divisor_compounds_multiple_splits():
    splits = [(date(2026, 1, 10), 2.0), (date(2026, 6, 1), 3.0)]
    # a price before both splits is divided by 2*3 = 6
    assert split_adjustment_divisor(date(2026, 1, 1), splits) == 6.0
    # between the two splits → only the later 3:1 applies
    assert split_adjustment_divisor(date(2026, 3, 1), splits) == 3.0


def test_apply_split_adjustment_makes_series_continuous():
    series = [(date(2026, 1, 5), 100.0), (date(2026, 1, 15), 60.0)]
    splits = [(date(2026, 1, 10), 2.0)]
    adj = apply_split_adjustment(series, splits)
    assert adj[0] == (date(2026, 1, 5), 50.0)   # 100 / 2 — no longer looks like a crash
    assert adj[1] == (date(2026, 1, 15), 60.0)  # post-split unchanged


def test_apply_split_adjustment_noop_without_splits():
    series = [(date(2026, 1, 5), 100.0)]
    assert apply_split_adjustment(series, []) == [(date(2026, 1, 5), 100.0)]


# ---------------------------------------------------------------------------
# DB queries (FakeConn)
# ---------------------------------------------------------------------------

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
async def test_upsert_corporate_actions_counts_and_skips_empty():
    conn = FakeConn()
    n = await ca_q.upsert_corporate_actions(conn, "AAPL", [
        {"action_date": date(2026, 1, 10), "action_type": "split", "ratio": 2.0, "amount": None},
    ])
    assert n == 1
    assert conn.executed  # executemany called
    assert await ca_q.upsert_corporate_actions(conn, "AAPL", []) == 0


@pytest.mark.asyncio
async def test_get_splits_parses_rows():
    conn = FakeConn(fetch=[{"action_date": date(2026, 1, 10), "ratio": 2.0}])
    out = await ca_q.get_splits(conn, "AAPL")
    assert out == [(date(2026, 1, 10), 2.0)]
