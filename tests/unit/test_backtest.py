"""Backtest realism: cost model, slippage/fee-adjusted fills, net-vs-gross."""
from datetime import datetime, timedelta, timezone

from backend.analytics.backtest import CostModel, run_backtest, _trade_returns


def test_cost_model_for_symbol_india_vs_us():
    ind = CostModel.for_symbol("RELIANCE.NS")
    us = CostModel.for_symbol("AAPL")
    assert ind.stt_bps_round_trip == 20.0      # India has STT
    assert us.stt_bps_round_trip == 0.0        # US commission-free
    assert ind.fee_fraction > us.fee_fraction
    assert CostModel.for_symbol("TCS.BO").stt_bps_round_trip == 20.0


def test_trade_returns_buy_net_below_gross():
    cm = CostModel(slippage_bps=5, fee_bps_round_trip=10, stt_bps_round_trip=20)  # 0.30% fees
    gross, net = _trade_returns("BUY", 100.0, 101.0, cm)
    assert gross == 0.01           # raw mid-price move
    assert net < gross             # slippage + fees eat into it
    assert 0.005 < net < 0.007     # ~1% - 0.1% slippage - 0.30% fees


def test_trade_returns_sell_inverts_direction():
    cm = CostModel(slippage_bps=0, fee_bps_round_trip=0, stt_bps_round_trip=0)
    gross, net = _trade_returns("SELL", 100.0, 99.0, cm)
    assert gross == 0.01           # price fell → short profits
    assert net == gross            # no costs configured


def _bullish_day(ts):
    return {"timestamp": ts, "rsi_14": 20.0, "sma_20": 90.0, "momentum_10": 0.06,
            "volatility_20": 0.10, "ema_9": 100.0, "ema_20": 95.0}


def test_run_backtest_net_below_gross_and_reports_assumptions():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dates = [base + timedelta(days=i) for i in range(12)]
    analytics_rows = [_bullish_day(d) for d in dates]
    ohlcv_rows = [{"timestamp": d, "open": 100.0, "high": 102.0, "low": 99.0,
                   "close": 101.0, "volume": 1_000_000} for d in dates]

    res = run_backtest(analytics_rows, ohlcv_rows, {}, cost_model=CostModel.for_symbol("AAPL"))

    assert res["trades"] > 0                       # bullish signals → BUY trades
    assert res["gross_return"] >= res["total_return"]
    assert res["cost_drag"] >= 0                    # costs always drag
    assert res["cost_model"]["stt_bps_round_trip"] == 0.0
    assert any("SURVIVORSHIP" in a for a in res["assumptions"])
    # daily rows carry both gross and net columns
    assert "gross_return" in res["daily"][0] and "daily_return" in res["daily"][0]
    assert res.get("mode") != "discrete"           # default path is the daily replay


def test_run_backtest_discrete_mode_capital_and_hold_days():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dates = [base + timedelta(days=i) for i in range(12)]
    analytics_rows = [_bullish_day(d) for d in dates]
    ohlcv_rows = [{"timestamp": d, "open": 100.0, "high": 102.0, "low": 99.0,
                   "close": 101.0, "volume": 1_000_000} for d in dates]

    res = run_backtest(analytics_rows, ohlcv_rows, {}, cost_model=CostModel.for_symbol("AAPL"),
                       hold_days=2, capital=100_000, position_fraction=0.5)

    assert res["mode"] == "discrete"
    assert res["hold_days"] == 2
    assert res["position_fraction"] == 0.5
    assert res["starting_capital"] == 100_000.0
    assert res["trades"] > 0
    assert "ending_equity" in res and "trades_log" in res
    assert any("Non-overlapping" in a for a in res["assumptions"])
