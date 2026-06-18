"""India market signals (P5): pure scorers + NSE parsers + engine integration + queries."""
from datetime import date

import pytest

from backend.decision.india_signals import (
    score_fii_dii, score_pcr, score_gift_nifty, score_india_market, INDIA_SIGNAL_WEIGHT,
)
from backend.decision.signals import compute_all_signals
from backend.ingest.india_signals import parse_fii_dii, parse_pcr
from backend.db.queries import india_signals as ind_q


# ---------------------------------------------------------------------------
# scorers
# ---------------------------------------------------------------------------

def test_score_fii_dii_levels():
    assert score_fii_dii(3000, 0) == 1.0
    assert score_fii_dii(700, 0) == 0.5
    assert score_fii_dii(-3000, 0) == -1.0
    assert score_fii_dii(100, 100) == 0.0      # net +200, within band
    assert score_fii_dii(None, None) is None


def test_score_pcr_is_contrarian():
    assert score_pcr(1.5) == 1.0       # heavy puts → contrarian bullish
    assert score_pcr(1.2) == 0.5
    assert score_pcr(0.5) == -1.0      # complacent calls → contrarian bearish
    assert score_pcr(1.0) == 0.0
    assert score_pcr(None) is None


def test_score_gift_nifty_directional():
    assert score_gift_nifty(0.01) == 1.0
    assert score_gift_nifty(0.002) == 0.5
    assert score_gift_nifty(-0.01) == -1.0
    assert score_gift_nifty(0.0) == 0.0
    assert score_gift_nifty(None) is None


def test_score_india_market_all_bullish():
    sig = score_india_market({"fii_net_cr": 3000, "dii_net_cr": 0, "pcr": 1.5, "gift_nifty_pct": 0.01})
    assert sig.name == "india_flow"
    assert sig.weight == INDIA_SIGNAL_WEIGHT
    assert sig.score == 1.0


def test_score_india_market_partial_data_only_uses_present():
    sig = score_india_market({"pcr": 1.5})     # only PCR present
    assert sig.score == 1.0
    assert sig.label == "pcr"


def test_score_india_market_none_and_empty_are_neutral():
    assert score_india_market(None).score == 0.0
    assert score_india_market(None).label == "neutral"
    assert score_india_market({}).score == 0.0
    assert score_india_market({"pcr": None}).label == "no_data"


# ---------------------------------------------------------------------------
# engine integration
# ---------------------------------------------------------------------------

def test_compute_all_signals_appends_india_only_with_context():
    base = compute_all_signals(close=100, rsi=50, sma_20=100, momentum_10=0.0, vol_20=0.2,
                               sentiment_score=None, predicted_close=None)
    assert all(s.name != "india_flow" for s in base)        # US path untouched

    withctx = compute_all_signals(close=100, rsi=50, sma_20=100, momentum_10=0.0, vol_20=0.2,
                                  sentiment_score=None, predicted_close=None,
                                  india_context={"pcr": 1.5})
    assert [s.name for s in withctx][-1] == "india_flow"
    assert len(withctx) == len(base) + 1


# ---------------------------------------------------------------------------
# NSE parsers (pure)
# ---------------------------------------------------------------------------

def test_parse_fii_dii_extracts_net_values():
    payload = [{"category": "FII/FPI **", "netValue": "1,234.5"},
               {"category": "DII **", "netValue": "-567.8"}]
    out = parse_fii_dii(payload)
    assert out["fii_net_cr"] == 1234.5
    assert out["dii_net_cr"] == -567.8


def test_parse_fii_dii_empty():
    assert parse_fii_dii(None) == {"fii_net_cr": None, "dii_net_cr": None}


def test_parse_pcr_sums_open_interest():
    payload = {"records": {"data": [
        {"PE": {"openInterest": 200}, "CE": {"openInterest": 100}},
        {"PE": {"openInterest": 100}, "CE": {"openInterest": 100}},
    ]}}
    assert parse_pcr(payload) == round(300 / 200, 4)        # 1.5


def test_parse_pcr_no_calls_returns_none():
    assert parse_pcr({"records": {"data": [{"PE": {"openInterest": 5}}]}}) is None
    assert parse_pcr({}) is None


# ---------------------------------------------------------------------------
# queries
# ---------------------------------------------------------------------------

class FakeConn:
    def __init__(self, fetchrow=None, fetch=None):
        self._fetchrow = fetchrow
        self._fetch = fetch or []
        self.calls = []

    async def fetchrow(self, q, *a):
        self.calls.append(q)
        return self._fetchrow

    async def fetch(self, q, *a):
        self.calls.append(q)
        return self._fetch

    async def execute(self, q, *a):
        self.calls.append(q)

    async def executemany(self, q, data):
        self.calls.append((q, data))


def test_market_context_shapes_row_or_none():
    row = {"fii_net_cr": 100, "dii_net_cr": -50, "pcr": 1.1, "gift_nifty_pct": 0.002}
    assert ind_q.market_context(row) == {
        "fii_net_cr": 100.0, "dii_net_cr": -50.0, "pcr": 1.1, "gift_nifty_pct": 0.002,
    }
    assert ind_q.market_context(None) is None


@pytest.mark.asyncio
async def test_upsert_bulk_deals_counts_and_skips_empty():
    conn = FakeConn()
    n = await ind_q.upsert_bulk_deals(conn, [{
        "deal_date": date(2026, 6, 1), "symbol": "X.NS", "client": "c",
        "side": "BUY", "quantity": 1, "price": 1.0, "deal_type": "bulk"}])
    assert n == 1
    assert await ind_q.upsert_bulk_deals(conn, []) == 0


@pytest.mark.asyncio
async def test_get_latest_market_signals_returns_row():
    row = {"date": date(2026, 6, 1), "pcr": 1.1}
    assert await ind_q.get_latest_market_signals(FakeConn(fetchrow=row)) == row
