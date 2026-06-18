"""R7 drift + R9 per-call attribution + R10 committee — pure-core tests."""
from unittest.mock import AsyncMock, patch

import pytest

from backend.analytics.drift import (
    VERDICT_DEGRADING, VERDICT_HEALTHY, VERDICT_INSUFFICIENT, VERDICT_RETRAIN,
    drift_verdict, model_health, rolling_hit_rate, signal_drift,
)
from backend.analytics.calibration import decompose_decision
from backend.llm.committee import parse_vote, risk_officer_gate, run_committee


def _scored(date_str: str, correct: bool, **kw) -> dict:
    return {"decision_date": date_str, "correct": correct, **kw}


def _series(start_correct: int, start_total: int, recent_correct: int, recent_total: int):
    """Baseline rows in March-May, recent rows in June."""
    rows = []
    for i in range(start_total):
        rows.append(_scored(f"2026-0{3 + i % 3}-{(i % 27) + 1:02d}", i < start_correct))
    for i in range(recent_total):
        rows.append(_scored(f"2026-06-{(i % 27) + 1:02d}", i < recent_correct))
    return rows


# ---------------------------------------------------------------------------
# R7: drift
# ---------------------------------------------------------------------------

def test_drift_healthy_when_stable():
    out = drift_verdict(_series(12, 20, 12, 20))
    assert out["status"] == VERDICT_HEALTHY


def test_drift_degrading_on_moderate_decay():
    # baseline 60% → recent 52% = -8pp
    out = drift_verdict(_series(12, 20, 13, 25))
    assert out["status"] == VERDICT_DEGRADING


def test_drift_retrain_on_severe_decay():
    # baseline 60% → recent 40% = -20pp
    out = drift_verdict(_series(12, 20, 8, 20))
    assert out["status"] == VERDICT_RETRAIN
    assert out["delta"] == pytest.approx(-0.20, abs=1e-6)


def test_drift_insufficient_on_thin_data():
    assert drift_verdict([_scored("2026-06-01", True)])["status"] == VERDICT_INSUFFICIENT
    assert drift_verdict([])["status"] == VERDICT_INSUFFICIENT


def test_rolling_hit_rate_windows():
    rows = _series(10, 20, 10, 20)
    out = rolling_hit_rate(rows, window_days=30, step_days=15)
    assert out, "expected at least one window"
    for w in out:
        assert 0 <= w["hit_rate"] <= 1
        assert w["count"] > 0


def test_signal_drift_trends():
    history = []
    for i, acc in enumerate([0.70, 0.65, 0.60, 0.52]):
        history.append({"snapshot_date": f"2026-0{i + 1}-01", "signal": "forecast", "accuracy": acc})
    for i, acc in enumerate([0.55, 0.56, 0.55, 0.56]):
        history.append({"snapshot_date": f"2026-0{i + 1}-01", "signal": "rsi", "accuracy": acc})
    out = {s["signal"]: s for s in signal_drift(history)}
    assert out["forecast"]["trend"] == "declining"
    assert out["rsi"]["trend"] == "stable"


def test_model_health_bundles_everything():
    out = model_health(_series(12, 20, 8, 20), [])
    assert out["verdict"] == VERDICT_RETRAIN
    assert "rolling" in out and "signal_drift" in out


# ---------------------------------------------------------------------------
# R9: per-call attribution
# ---------------------------------------------------------------------------

def test_decompose_sums_to_strategy_return():
    row = {
        "signals": {
            "sentiment": {"score": 1.0, "weight": 0.22},
            "momentum": {"score": 0.5, "weight": 0.12},
            "rsi": {"score": 0.0, "weight": 0.12},
        },
        "weighted_score": 1.0 * 0.22 + 0.5 * 0.12,
        "strategy_return": 0.046,
    }
    parts = decompose_decision(row)
    total = sum(p["contribution"] for p in parts if p["contribution"] is not None)
    assert total == pytest.approx(0.046, abs=1e-4)
    by_name = {p["signal"]: p for p in parts}
    assert by_name["rsi"]["contribution"] == 0.0          # inactive signal earns nothing
    assert by_name["sentiment"]["contribution"] > by_name["momentum"]["contribution"]
    assert parts[0]["signal"] == "sentiment"               # sorted by |contribution|


def test_decompose_zero_conviction_row():
    parts = decompose_decision({"signals": {"rsi": {"score": 0.0, "weight": 0.12}},
                                "weighted_score": 0.0, "strategy_return": 0.0})
    assert all(p["share"] == 0.0 for p in parts)


# ---------------------------------------------------------------------------
# R10: committee
# ---------------------------------------------------------------------------

def test_parse_vote():
    assert parse_vote("Strong setup overall.\nVOTE: BUY") == "BUY"
    assert parse_vote("vote: hold") == "HOLD"
    assert parse_vote("no vote line") is None
    assert parse_vote("") is None


def test_risk_gate_passes_calm_conditions():
    out = risk_officer_gate("BUY", vol_20=0.20, regime="bull", days_to_earnings=30)
    assert out == {"vetoed": False, "reasons": []}


def test_risk_gate_vetoes_extreme_vol():
    out = risk_officer_gate("BUY", vol_20=0.60, regime="bull", days_to_earnings=None)
    assert out["vetoed"] and "volatility" in out["reasons"][0]


def test_risk_gate_vetoes_high_vol_regime_and_imminent_earnings():
    out = risk_officer_gate("SELL", vol_20=0.20, regime="high_vol", days_to_earnings=2)
    assert out["vetoed"] and len(out["reasons"]) == 2


def test_risk_gate_never_vetoes_hold():
    out = risk_officer_gate("HOLD", vol_20=0.99, regime="high_vol", days_to_earnings=0)
    assert not out["vetoed"]


@pytest.mark.asyncio
async def test_run_committee_parallel_views_and_veto():
    async def fake_complete(label, prompt):
        if label == "risk_officer":
            return "Too risky right now."
        return f"{label} analysis.\nVOTE: BUY"

    with patch("backend.llm.committee._safe_complete", AsyncMock(side_effect=fake_complete)):
        out = await run_committee(
            symbol="AAPL", recommendation="BUY", confidence=0.8,
            signals_json={"volatility": {"score": -1.0, "weight": 0.08, "value": 0.6, "label": "extreme"}},
            vol_20=0.60, regime="bull",
        )
    assert set(out["views"]) == {"technical", "fundamental", "macro", "sentiment"}
    assert out["votes"]["technical"] == "BUY"
    assert out["vetoed"] is True
    assert out["final_recommendation"] == "HOLD"
    assert out["engine_recommendation"] == "BUY"
    assert out["risk_officer"] == "Too risky right now."


@pytest.mark.asyncio
async def test_run_committee_endorses_when_calm():
    with patch("backend.llm.committee._safe_complete",
               AsyncMock(side_effect=lambda label, prompt: f"{label} ok.\nVOTE: BUY")):
        out = await run_committee(
            symbol="AAPL", recommendation="BUY", confidence=0.8,
            signals_json={}, vol_20=0.20, regime="bull", days_to_earnings=30,
        )
    assert out["vetoed"] is False
    assert out["final_recommendation"] == "BUY"


@pytest.mark.asyncio
async def test_run_committee_degrades_on_agent_failure():
    async def flaky(label, prompt):
        if label == "fundamental":
            return ""
        return "view.\nVOTE: HOLD"

    with patch("backend.llm.committee._safe_complete", AsyncMock(side_effect=flaky)):
        out = await run_committee(symbol="AAPL", recommendation="HOLD", confidence=0.5,
                                  signals_json={})
    assert out["views"]["fundamental"] == ""
    assert out["votes"]["fundamental"] is None
    assert out["final_recommendation"] == "HOLD"


@pytest.mark.asyncio
async def test_run_committee_flags_llm_unavailable_when_all_fail():
    # Every agent returns "" (e.g. all 429 rate-limited) → llm_available False,
    # so the UI won't falsely claim an endorsement. Deterministic veto still applies.
    with patch("backend.llm.committee._safe_complete", AsyncMock(return_value="")):
        out = await run_committee(symbol="AAPL", recommendation="BUY", confidence=0.8,
                                  signals_json={}, vol_20=0.20, regime="bull")
    assert out["llm_available"] is False
    assert all(v is None for v in out["votes"].values())
    assert out["final_recommendation"] == "BUY"  # no veto, engine rec stands


@pytest.mark.asyncio
async def test_run_committee_llm_available_when_any_agent_responds():
    with patch("backend.llm.committee._safe_complete",
               AsyncMock(side_effect=lambda label, prompt: "" if label == "risk_officer" else "view.\nVOTE: BUY")):
        out = await run_committee(symbol="AAPL", recommendation="BUY", confidence=0.8,
                                  signals_json={}, vol_20=0.20, regime="bull", days_to_earnings=30)
    assert out["llm_available"] is True
