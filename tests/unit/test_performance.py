"""Recommendation accuracy: price resolution, scoring, aggregation, decision-scoring loop."""
from datetime import date, datetime, timezone

import pytest

from backend.analytics.performance import (
    resolve_price, evaluate_decision, aggregate_performance, HOLD_BAND,
)
from backend.api.routers.performance import _score_decisions


_SERIES = [
    (date(2026, 1, 1), 100.0),
    (date(2026, 1, 3), 110.0),
    (date(2026, 1, 6), 120.0),
]


# ---------------------------------------------------------------------------
# resolve_price
# ---------------------------------------------------------------------------

def test_resolve_on_or_before_picks_latest_prior():
    assert resolve_price(_SERIES, date(2026, 1, 4), "on_or_before") == 110.0
    assert resolve_price(_SERIES, date(2026, 1, 1), "on_or_before") == 100.0


def test_resolve_on_or_before_none_when_too_early():
    assert resolve_price(_SERIES, date(2025, 12, 31), "on_or_before") is None


def test_resolve_on_or_after_picks_earliest_following():
    assert resolve_price(_SERIES, date(2026, 1, 4), "on_or_after") == 120.0
    assert resolve_price(_SERIES, date(2026, 1, 3), "on_or_after") == 110.0


def test_resolve_on_or_after_none_when_too_late():
    assert resolve_price(_SERIES, date(2026, 1, 7), "on_or_after") is None


def test_resolve_empty_series():
    assert resolve_price([], date(2026, 1, 1), "on_or_before") is None


# ---------------------------------------------------------------------------
# evaluate_decision
# ---------------------------------------------------------------------------

def test_evaluate_buy_win_and_loss():
    win = evaluate_decision("BUY", 100.0, 110.0)
    assert win["correct"] is True and win["strategy_return"] == 0.1
    loss = evaluate_decision("BUY", 100.0, 90.0)
    assert loss["correct"] is False and loss["strategy_return"] == -0.1


def test_evaluate_sell_inverts_direction():
    win = evaluate_decision("SELL", 100.0, 90.0)
    assert win["correct"] is True and win["strategy_return"] == 0.1
    loss = evaluate_decision("SELL", 100.0, 110.0)
    assert loss["correct"] is False and loss["strategy_return"] == -0.1


def test_evaluate_hold_uses_band_and_zero_return():
    inside = evaluate_decision("HOLD", 100.0, 100.0 + 100.0 * HOLD_BAND)
    assert inside["correct"] is True and inside["strategy_return"] == 0.0
    outside = evaluate_decision("HOLD", 100.0, 110.0)
    assert outside["correct"] is False and outside["strategy_return"] == 0.0


def test_evaluate_none_on_missing_or_zero_price():
    assert evaluate_decision("BUY", None, 110.0) is None
    assert evaluate_decision("BUY", 100.0, None) is None
    assert evaluate_decision("BUY", 0.0, 110.0) is None


# ---------------------------------------------------------------------------
# aggregate_performance
# ---------------------------------------------------------------------------

def test_aggregate_overall_and_breakdowns():
    evaluated = [
        {"recommendation": "BUY",  "risk_level": "Low",  "strategy_return": 0.1,  "correct": True},
        {"recommendation": "BUY",  "risk_level": "High", "strategy_return": -0.05, "correct": False},
        {"recommendation": "SELL", "risk_level": "Low",  "strategy_return": 0.2,  "correct": True},
    ]
    agg = aggregate_performance(evaluated)

    assert agg["overall"]["count"] == 3
    assert agg["overall"]["hit_rate"] == round(2 / 3, 4)
    assert agg["overall"]["avg_return"] == round((0.1 - 0.05 + 0.2) / 3, 6)

    assert agg["by_recommendation"]["BUY"] == {"count": 2, "hit_rate": 0.5, "avg_return": 0.025}
    assert agg["by_recommendation"]["SELL"]["hit_rate"] == 1.0
    assert "HOLD" not in agg["by_recommendation"]

    assert agg["by_risk_level"]["Low"]["count"] == 2
    assert agg["by_risk_level"]["High"]["hit_rate"] == 0.0

    # 1.1 * 0.95 * 1.2 - 1
    assert agg["cumulative_return"] == round(1.1 * 0.95 * 1.2 - 1.0, 6)


def test_aggregate_empty():
    agg = aggregate_performance([])
    assert agg["overall"] == {"count": 0, "hit_rate": None, "avg_return": None}
    assert agg["by_recommendation"] == {}
    assert agg["cumulative_return"] == 0.0


# ---------------------------------------------------------------------------
# _score_decisions (router pure helper)
# ---------------------------------------------------------------------------

def _dec(symbol, rec, created, risk="Low", conf=0.8):
    return {"symbol": symbol, "recommendation": rec, "risk_level": risk,
            "confidence": conf, "created_at": created}


def test_score_decisions_evaluates_elapsed_skips_pending_and_no_price():
    today = date(2026, 2, 1)
    decisions = [
        _dec("AAPL", "BUY", datetime(2026, 1, 1, tzinfo=timezone.utc)),   # elapsed → scored
        _dec("AAPL", "BUY", datetime(2026, 1, 30, tzinfo=timezone.utc)),  # horizon not elapsed → pending
        _dec("MSFT", "SELL", datetime(2026, 1, 1, tzinfo=timezone.utc)),  # no price series → skipped
    ]
    closes = {"AAPL": [(date(2026, 1, 1), 100.0), (date(2026, 1, 6), 110.0)]}

    evaluated = _score_decisions(decisions, closes, horizon_days=5, today=today)

    assert len(evaluated) == 1
    row = evaluated[0]
    assert row["symbol"] == "AAPL"
    assert row["entry_price"] == 100.0
    assert row["exit_price"] == 110.0
    assert row["strategy_return"] == 0.1
    assert row["correct"] is True
    assert row["decision_date"] == "2026-01-01"
