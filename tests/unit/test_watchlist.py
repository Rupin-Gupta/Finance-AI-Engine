"""Watchlist: pure P&L enrichment + DB query helpers."""
import pytest

from backend.api.routers.watchlist import _enrich
from backend.db.queries import watchlist as wl_q
from backend.db.queries import market_data as md_q
from backend.db.queries import decisions as dec_q
from backend.db.queries import sentiment as sent_q


# ---------------------------------------------------------------------------
# _enrich — pure P&L / totals (no I/O)
# ---------------------------------------------------------------------------

def test_enrich_computes_position_pnl_and_totals():
    items = [
        {"symbol": "AAPL", "quantity": 10.0, "cost_basis": 100.0, "note": None},
        {"symbol": "MSFT", "quantity": None, "cost_basis": None, "note": "watch only"},
    ]
    prices = {"AAPL": 150.0, "MSFT": 400.0}
    decisions = {"AAPL": {"symbol": "AAPL", "recommendation": "BUY",
                          "confidence": 0.8, "risk_level": "Low", "created_at": None}}
    sentiment = {"AAPL": 0.42}

    enriched, totals = _enrich(items, prices, decisions, sentiment)

    aapl = enriched[0]
    assert aapl["current_price"] == 150.0
    assert aapl["market_value"] == 1500.0
    assert aapl["unrealized_pnl"] == 500.0
    assert aapl["unrealized_pnl_pct"] == 0.5
    assert aapl["recommendation"] == "BUY"
    assert aapl["confidence"] == 0.8
    assert aapl["sentiment_score"] == 0.42

    # watch-only row: no qty/cost → no P&L, no decision/sentiment
    msft = enriched[1]
    assert msft["market_value"] is None
    assert msft["unrealized_pnl"] is None
    assert msft["recommendation"] is None
    assert msft["sentiment_score"] is None

    assert totals == {
        "positions": 2,
        "market_value": 1500.0,
        "cost_value": 1000.0,
        "unrealized_pnl": 500.0,
        "unrealized_pnl_pct": 0.5,
    }


def test_enrich_handles_missing_price():
    items = [{"symbol": "AAPL", "quantity": 5.0, "cost_basis": 100.0, "note": None}]
    enriched, totals = _enrich(items, prices={}, decisions={}, sentiment={})
    row = enriched[0]
    assert row["current_price"] is None
    assert row["market_value"] is None
    assert row["unrealized_pnl"] is None
    assert totals["market_value"] == 0.0
    assert totals["unrealized_pnl_pct"] is None


def test_enrich_negative_pnl():
    items = [{"symbol": "TSLA", "quantity": 2.0, "cost_basis": 300.0, "note": None}]
    enriched, totals = _enrich(items, {"TSLA": 250.0}, {}, {})
    assert enriched[0]["unrealized_pnl"] == -100.0
    assert enriched[0]["unrealized_pnl_pct"] == round((250.0 - 300.0) / 300.0, 4)
    assert totals["unrealized_pnl"] == -100.0


def test_enrich_adds_suggested_position_pct():
    items = [{"symbol": "AAPL", "quantity": 10.0, "cost_basis": 100.0, "note": None}]
    decisions = {"AAPL": {"symbol": "AAPL", "recommendation": "BUY",
                          "confidence": 0.8, "risk_level": "Low", "created_at": None}}
    calibration = {"reliability": {"bins": [
        {"bin_lower": 0.8, "bin_upper": 0.9, "count": 20,
         "mean_confidence": 0.8, "hit_rate": 0.8, "gap": 0.0}]}}
    enriched, _ = _enrich(items, {"AAPL": 150.0}, decisions, {}, calibration)
    assert enriched[0]["suggested_position_pct"] is not None
    assert 0.0 < enriched[0]["suggested_position_pct"] <= 0.20


def test_enrich_no_decision_no_size():
    items = [{"symbol": "MSFT", "quantity": None, "cost_basis": None, "note": None}]
    enriched, _ = _enrich(items, {}, {}, {})
    assert enriched[0]["suggested_position_pct"] is None


# ---------------------------------------------------------------------------
# DB query helpers (FakeConn)
# ---------------------------------------------------------------------------

class FakeConn:
    def __init__(self, fetchrow=None, fetch=None, execute_result="DELETE 1"):
        self._fetchrow = fetchrow
        self._fetch = fetch or []
        self._execute_result = execute_result
        self.calls = []

    async def fetchrow(self, q, *args):
        self.calls.append(("fetchrow", q, args))
        return self._fetchrow

    async def fetch(self, q, *args):
        self.calls.append(("fetch", q, args))
        return self._fetch

    async def execute(self, q, *args):
        self.calls.append(("execute", q, args))
        return self._execute_result


@pytest.mark.asyncio
async def test_upsert_watchlist_item_returns_row():
    stored = {"symbol": "AAPL", "quantity": 10.0, "cost_basis": 100.0,
              "note": "core", "created_at": None, "updated_at": None}
    conn = FakeConn(fetchrow=stored)
    row = await wl_q.upsert_watchlist_item(
        conn, {"symbol": "AAPL", "quantity": 10.0, "cost_basis": 100.0, "note": "core"}
    )
    assert row == stored
    assert conn.calls[0][2] == ("AAPL", 10.0, 100.0, "core")


@pytest.mark.asyncio
async def test_delete_watchlist_item_true_false():
    assert await wl_q.delete_watchlist_item(FakeConn(execute_result="DELETE 1"), "AAPL") is True
    assert await wl_q.delete_watchlist_item(FakeConn(execute_result="DELETE 0"), "AAPL") is False


@pytest.mark.asyncio
async def test_get_latest_prices_maps_symbol_to_close():
    conn = FakeConn(fetch=[{"symbol": "AAPL", "close": 150.0},
                           {"symbol": "MSFT", "close": 400.0}])
    out = await md_q.get_latest_prices(conn, ["AAPL", "MSFT"])
    assert out == {"AAPL": 150.0, "MSFT": 400.0}


@pytest.mark.asyncio
async def test_get_latest_prices_empty_symbols_skips_query():
    conn = FakeConn()
    assert await md_q.get_latest_prices(conn, []) == {}
    assert conn.calls == []


@pytest.mark.asyncio
async def test_get_latest_decisions_multi_keys_by_symbol():
    rows = [{"symbol": "AAPL", "recommendation": "BUY", "confidence": 0.8,
             "risk_level": "Low", "created_at": None}]
    out = await dec_q.get_latest_decisions_multi(FakeConn(fetch=rows), ["AAPL"])
    assert out["AAPL"]["recommendation"] == "BUY"


@pytest.mark.asyncio
async def test_get_latest_sentiment_multi_drops_null_scores():
    rows = [{"symbol": "AAPL", "score": 0.3}, {"symbol": "MSFT", "score": None}]
    out = await sent_q.get_latest_sentiment_multi(FakeConn(fetch=rows), ["AAPL", "MSFT"])
    assert out == {"AAPL": 0.3}
