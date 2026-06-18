"""Paper trading: pure execution engine + portfolio metrics + queries."""
import pytest

from backend.analytics.backtest import CostModel
from backend.analytics.paper_trading import (
    execute_trade, portfolio_metrics, plan_rebalance, equity_curve_metrics,
)
from backend.db.queries import paper as paper_q

ZERO = CostModel(slippage_bps=0, fee_bps_round_trip=0, stt_bps_round_trip=0)


# ---------------------------------------------------------------------------
# execute_trade
# ---------------------------------------------------------------------------

def test_buy_reduces_cash_and_sets_avg_cost():
    cash, pos, trade = execute_trade(100_000, {}, "BUY", "AAPL", 10, 100.0, ZERO)
    assert cash == 99_000          # 10 * 100, no fees
    assert pos["AAPL"] == {"quantity": 10, "avg_cost": 100.0}
    assert trade["realized_pnl"] is None


def test_buy_again_averages_cost():
    cash, pos, _ = execute_trade(99_000, {"AAPL": {"quantity": 10, "avg_cost": 100.0}},
                                 "BUY", "AAPL", 10, 120.0, ZERO)
    assert pos["AAPL"]["quantity"] == 20
    assert pos["AAPL"]["avg_cost"] == 110.0   # (1000 + 1200) / 20
    assert cash == 97_800


def test_sell_realizes_pnl_and_frees_cash():
    start = {"AAPL": {"quantity": 20, "avg_cost": 110.0}}
    cash, pos, trade = execute_trade(97_800, start, "SELL", "AAPL", 5, 130.0, ZERO)
    assert trade["realized_pnl"] == 100.0     # (130-110)*5
    assert cash == 98_450                      # +650 proceeds
    assert pos["AAPL"]["quantity"] == 15
    assert pos["AAPL"]["avg_cost"] == 110.0


def test_full_sell_removes_position():
    _, pos, _ = execute_trade(0, {"AAPL": {"quantity": 5, "avg_cost": 100.0}},
                              "SELL", "AAPL", 5, 110.0, ZERO)
    assert "AAPL" not in pos


def test_buy_applies_costs():
    cm = CostModel(slippage_bps=10, fee_bps_round_trip=20, stt_bps_round_trip=0)  # per-side 0.20%
    cash, _, trade = execute_trade(100_000, {}, "BUY", "AAPL", 10, 100.0, cm)
    assert trade["fee"] == 2.0                 # 1000 * 0.002
    assert cash == 100_000 - 1002.0


def test_insufficient_cash_raises():
    with pytest.raises(ValueError, match="insufficient cash"):
        execute_trade(100, {}, "BUY", "AAPL", 10, 100.0, ZERO)


def test_insufficient_shares_raises():
    with pytest.raises(ValueError, match="insufficient shares"):
        execute_trade(0, {}, "SELL", "AAPL", 5, 100.0, ZERO)


def test_bad_input_raises():
    with pytest.raises(ValueError):
        execute_trade(100_000, {}, "BUY", "AAPL", -1, 100.0, ZERO)
    with pytest.raises(ValueError):
        execute_trade(100_000, {}, "HOLD", "AAPL", 1, 100.0, ZERO)


def test_execute_does_not_mutate_caller_positions():
    original = {"AAPL": {"quantity": 10, "avg_cost": 100.0}}
    execute_trade(99_000, original, "BUY", "AAPL", 5, 120.0, ZERO)
    assert original["AAPL"] == {"quantity": 10, "avg_cost": 100.0}  # unchanged


# ---------------------------------------------------------------------------
# portfolio_metrics
# ---------------------------------------------------------------------------

def test_portfolio_metrics_mark_to_market():
    m = portfolio_metrics(
        cash=98_450,
        positions={"AAPL": {"quantity": 15, "avg_cost": 110.0}},
        prices={"AAPL": 130.0},
        starting_cash=100_000,
    )
    assert m["positions_value"] == 1950.0
    assert m["equity"] == 100_400.0
    assert m["unrealized_pnl"] == 300.0
    assert m["total_return"] == 0.004


def test_portfolio_metrics_flags_unpriced():
    m = portfolio_metrics(50_000, {"XYZ": {"quantity": 1, "avg_cost": 10.0}}, {}, 50_000)
    assert m["unpriced_symbols"] == ["XYZ"]
    assert m["positions_value"] == 0.0


# ---------------------------------------------------------------------------
# plan_rebalance (R1.1 / R2.3 auto-exec sizing → order)
# ---------------------------------------------------------------------------

def test_plan_rebalance_buy_tops_up_to_target():
    o = plan_rebalance("BUY", 0.20, 100_000, 100.0, current_qty=0)
    assert o == {"side": "BUY", "quantity": 200.0}     # floor(0.2*100000/100)


def test_plan_rebalance_buy_no_action_when_at_target():
    assert plan_rebalance("BUY", 0.20, 100_000, 100.0, current_qty=200) is None


def test_plan_rebalance_sell_closes_position():
    assert plan_rebalance("SELL", 0.0, 100_000, 100.0, current_qty=10) == {"side": "SELL", "quantity": 10}


def test_plan_rebalance_hold_and_no_edge_are_noops():
    assert plan_rebalance("HOLD", 0.20, 100_000, 100.0, current_qty=0) is None
    assert plan_rebalance("BUY", 0.0, 100_000, 100.0, current_qty=0) is None
    assert plan_rebalance("SELL", 0.0, 100_000, 100.0, current_qty=0) is None  # nothing to sell


# ---------------------------------------------------------------------------
# equity_curve_metrics (R1.2)
# ---------------------------------------------------------------------------

def test_equity_curve_metrics_basic():
    hist = [{"equity": 100_000}, {"equity": 101_000}, {"equity": 102_000}]
    m = equity_curve_metrics(hist, trades=[{"realized_pnl": 50}, {"realized_pnl": -10}])
    assert m["points"] == 3
    assert m["total_return"] == round(2000 / 100_000, 6)
    assert m["max_drawdown"] == 0.0
    assert m["win_rate"] == 0.5


def test_equity_curve_metrics_drawdown():
    hist = [{"equity": 100}, {"equity": 120}, {"equity": 90}]
    m = equity_curve_metrics(hist)
    assert m["max_drawdown"] == round((120 - 90) / 120, 6)


def test_equity_curve_metrics_insufficient_history():
    m = equity_curve_metrics([{"equity": 100}])
    assert m["total_return"] is None and m["sharpe"] is None


# ---------------------------------------------------------------------------
# queries (FakeConn)
# ---------------------------------------------------------------------------

class FakeConn:
    def __init__(self, existing=None):
        self._existing = existing
        self.calls = []

    async def fetchrow(self, q, *args):
        self.calls.append(("fetchrow", q, args))
        if "SELECT" in q:
            return self._existing
        return {"name": args[0], "starting_cash": args[1], "cash": args[1]}  # INSERT RETURNING

    async def execute(self, q, *args):
        self.calls.append(("execute", q, args))

    async def fetch(self, q, *args):
        return []


@pytest.mark.asyncio
async def test_get_or_create_portfolio_creates_when_missing():
    conn = FakeConn(existing=None)
    row = await paper_q.get_or_create_portfolio(conn, 100_000.0)
    assert row["cash"] == 100_000.0
    assert row["starting_cash"] == 100_000.0


@pytest.mark.asyncio
async def test_get_or_create_portfolio_returns_existing():
    existing = {"name": "default", "starting_cash": 50_000, "cash": 42_000}
    row = await paper_q.get_or_create_portfolio(FakeConn(existing=existing), 100_000.0)
    assert row["cash"] == 42_000
