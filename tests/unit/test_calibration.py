"""Confidence calibration: reliability curve, signal edge, threshold tuning, scorer."""
import json
from datetime import date, datetime, timezone

from backend.analytics.calibration import (
    reliability_curve, signal_contribution, tune_thresholds,
    calibration_summary, lookup_calibrated_prob,
)
from backend.api.routers.calibration import _score_for_calibration, _weighted_score


# ---------------------------------------------------------------------------
# reliability_curve
# ---------------------------------------------------------------------------

def test_reliability_curve_ece_and_brier():
    rows = [
        {"confidence": 0.9, "correct": True},
        {"confidence": 0.9, "correct": True},
        {"confidence": 0.1, "correct": False},
        {"confidence": 0.1, "correct": False},
    ]
    rc = reliability_curve(rows)
    assert rc["count"] == 4
    assert len(rc["bins"]) == 2
    # ECE = 0.5*|1.0-0.9| + 0.5*|0.0-0.1| = 0.1 ; Brier = mean(0.01 each) = 0.01
    assert rc["ece"] == 0.1
    assert rc["brier_score"] == 0.01


def test_reliability_curve_empty():
    rc = reliability_curve([])
    assert rc == {"count": 0, "bins": [], "brier_score": None, "ece": None}


# ---------------------------------------------------------------------------
# signal_contribution
# ---------------------------------------------------------------------------

def test_signal_contribution_directional_accuracy():
    rows = [
        {"realized_move": 0.05, "signals": {"rsi": {"score": 1.0, "weight": 0.12},
                                            "trend": {"score": -1.0, "weight": 0.16}}},
        {"realized_move": 0.04, "signals": {"rsi": {"score": 0.5, "weight": 0.12},
                                            "trend": {"score": -0.5, "weight": 0.16}}},
    ]
    out = {s["signal"]: s for s in signal_contribution(rows)}
    # both moves up; rsi pointed up twice (correct), trend pointed down twice (wrong)
    assert out["rsi"]["accuracy"] == 1.0
    assert out["rsi"]["active_count"] == 2
    assert out["trend"]["accuracy"] == 0.0


def test_signal_contribution_skips_zero_score_and_flat_move():
    rows = [
        {"realized_move": 0.0, "signals": {"rsi": {"score": 1.0, "weight": 0.1}}},   # flat → skipped
        {"realized_move": 0.03, "signals": {"rsi": {"score": 0.0, "weight": 0.1}}},  # zero score → skipped
    ]
    assert signal_contribution(rows) == []


def test_signal_contribution_return_attribution_is_additive():
    sigs = {"rsi": {"score": 1.0, "weight": 0.6}, "trend": {"score": 1.0, "weight": 0.4}}
    rows = [
        {"realized_move": 0.10, "strategy_return": 0.10, "weighted_score": 1.0, "signals": sigs},
        {"realized_move": -0.05, "strategy_return": -0.05, "weighted_score": 1.0, "signals": sigs},
    ]
    out = {s["signal"]: s for s in signal_contribution(rows)}
    # shares 0.6 / 0.4 of each decision's return → summed across rows
    assert out["rsi"]["attributed_return"] == 0.03    # 0.6*0.10 + 0.6*(-0.05)
    assert out["trend"]["attributed_return"] == 0.02
    # attribution reconstructs total strategy return (0.05)
    assert round(out["rsi"]["attributed_return"] + out["trend"]["attributed_return"], 6) == 0.05
    assert out["rsi"]["return_share"] == 0.6


# ---------------------------------------------------------------------------
# tune_thresholds
# ---------------------------------------------------------------------------

def test_tune_thresholds_picks_best_and_reports_current():
    rows = [{"weighted_score": 0.5, "realized_move": 0.05} for _ in range(5)]
    out = tune_thresholds(rows, current_threshold=0.30)
    # all BUY + all up → perfect hit rate; low thresholds keep all 5 as trades
    assert out["best"]["hit_rate"] == 1.0
    assert out["best"]["threshold"] == 0.10
    assert out["current"]["threshold"] == 0.30
    assert out["current_threshold"] == 0.30


def test_tune_thresholds_empty():
    assert tune_thresholds([]) == {"current": None, "grid": [], "best": None}


def test_weighted_score_from_signals():
    signals = {"rsi": {"score": 1.0, "weight": 0.12}, "trend": {"score": 0.5, "weight": 0.16}}
    assert _weighted_score(signals) == 0.12 + 0.08


# ---------------------------------------------------------------------------
# calibration_summary + lookup_calibrated_prob (R2.1 calibrated win prob)
# ---------------------------------------------------------------------------

def test_calibration_summary_buckets_and_per_recommendation():
    scored = [
        {"confidence": 0.9, "correct": True, "recommendation": "BUY"},
        {"confidence": 0.9, "correct": False, "recommendation": "BUY"},
        {"confidence": 0.2, "correct": False, "recommendation": "SELL"},
    ]
    s = calibration_summary(scored)
    assert s["count"] == 3
    assert s["by_recommendation"]["BUY"] == {"count": 2, "hit_rate": 0.5}
    assert s["overall_hit_rate"] == round(1 / 3, 4)


def test_lookup_calibrated_prob_uses_bin_hit_rate():
    scored = [
        {"confidence": 0.9, "correct": True, "recommendation": "BUY"},
        {"confidence": 0.9, "correct": False, "recommendation": "BUY"},
    ]
    bins = calibration_summary(scored)["reliability"]["bins"]
    assert lookup_calibrated_prob(bins, 0.9, min_count=1) == 0.5     # 1 of 2 correct


def test_lookup_calibrated_prob_empty_falls_back():
    assert lookup_calibrated_prob([], 0.7) == 0.7
    assert lookup_calibrated_prob([], None, fallback=0.3) == 0.3
    assert lookup_calibrated_prob(None, 0.6) == 0.6


# ---------------------------------------------------------------------------
# _score_for_calibration (router helper)
# ---------------------------------------------------------------------------

def _dec(symbol, rec, created, signals_json, conf=0.8, risk="Low"):
    return {"symbol": symbol, "recommendation": rec, "confidence": conf,
            "risk_level": risk, "signals_json": signals_json, "created_at": created}


def test_score_for_calibration_parses_signals_and_skips_pending():
    today = date(2026, 2, 1)
    sigs = {"rsi": {"score": 1.0, "weight": 0.12}, "trend": {"score": 0.5, "weight": 0.16}}
    decisions = [
        _dec("AAPL", "BUY", datetime(2026, 1, 1, tzinfo=timezone.utc), sigs),                 # dict signals
        _dec("AAPL", "BUY", datetime(2026, 1, 2, tzinfo=timezone.utc), json.dumps(sigs)),     # JSON-string signals
        _dec("AAPL", "BUY", datetime(2026, 1, 30, tzinfo=timezone.utc), sigs),                # pending → skipped
    ]
    closes = {"AAPL": [(date(2026, 1, 1), 100.0), (date(2026, 1, 6), 110.0),
                       (date(2026, 1, 7), 110.0)]}

    scored = _score_for_calibration(decisions, closes, horizon_days=5, today=today)

    assert len(scored) == 2
    row = scored[0]
    assert row["weighted_score"] == 0.2          # 1.0*0.12 + 0.5*0.16
    assert row["realized_move"] == 0.1
    assert row["strategy_return"] == 0.1          # BUY, price up
    assert row["correct"] is True
    assert "rsi" in row["signals"]
    # second decision's signals came in as a JSON string and were parsed
    assert scored[1]["signals"]["rsi"]["score"] == 1.0
