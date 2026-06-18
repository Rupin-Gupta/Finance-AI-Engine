"""R8 macro-event gate: curated calendar, nearest-event selection, confidence cap, engine wiring."""
from datetime import date

import pytest

from backend.ingest.events import fetch_market_events
from backend.analytics.events import (
    event_confidence_cap, nearest_gating_event, region_matches,
)
from backend.decision.signals import SignalResult
from backend.decision.engine import make_recommendation


# ---------------------------------------------------------------------------
# curated calendar
# ---------------------------------------------------------------------------

def test_fetch_returns_upcoming_within_horizon_only():
    today = date(2026, 6, 17)
    events = fetch_market_events(today, horizon_days=120)
    assert events, "expected upcoming events"
    for e in events:
        assert today <= e["event_date"] <= date(2026, 10, 15)
        assert e["region"] in ("US", "INDIA", "GLOBAL")
        assert e["impact"] in ("high", "medium", "low")
    # sorted ascending
    dates = [e["event_date"] for e in events]
    assert dates == sorted(dates)


def test_fetch_includes_high_impact_central_bank_events():
    events = fetch_market_events(date(2026, 7, 1), horizon_days=120)
    types = {e["event_type"] for e in events}
    assert "FOMC" in types          # Jul 29 within window
    assert "RBI_MPC" in types       # Aug 5 within window
    assert any(e["impact"] == "high" for e in events)


def test_fetch_generates_monthly_cpi():
    events = fetch_market_events(date(2026, 6, 17), horizon_days=120)
    cpi = [e for e in events if e["event_type"] == "CPI"]
    assert len(cpi) >= 2
    assert all(e["region"] == "US" and e["impact"] == "medium" for e in cpi)


# ---------------------------------------------------------------------------
# region matching
# ---------------------------------------------------------------------------

def test_region_matches():
    assert region_matches("GLOBAL", "US")
    assert region_matches("GLOBAL", "INDIA")
    assert region_matches("US", "US")
    assert not region_matches("US", "INDIA")
    assert not region_matches("INDIA", "US")


# ---------------------------------------------------------------------------
# nearest gating event
# ---------------------------------------------------------------------------

def _ev(d, region="US", impact="high", etype="FOMC"):
    return {"event_date": d, "region": region, "impact": impact,
            "event_type": etype, "title": f"{etype} {d}"}


def test_nearest_picks_closest_matching_region():
    today = date(2026, 6, 17)
    events = [
        _ev(date(2026, 6, 25), region="INDIA"),   # wrong region
        _ev(date(2026, 6, 20), region="US"),       # nearest US
        _ev(date(2026, 6, 30), region="US"),
    ]
    out = nearest_gating_event(events, today, "US")
    assert out["days_to_event"] == 3
    assert out["event_date"] == "2026-06-20"


def test_nearest_global_event_gates_any_market():
    today = date(2026, 6, 17)
    out = nearest_gating_event([_ev(date(2026, 6, 18), region="GLOBAL")], today, "INDIA")
    assert out is not None and out["days_to_event"] == 1


def test_nearest_ignores_low_impact_and_past_and_far():
    today = date(2026, 6, 17)
    events = [
        _ev(date(2026, 6, 18), impact="low"),       # low → ignored for gating
        _ev(date(2026, 6, 10)),                       # past
        _ev(date(2026, 7, 30)),                       # beyond max_days=14
    ]
    assert nearest_gating_event(events, today, "US") is None


def test_nearest_tie_breaks_toward_high_impact():
    today = date(2026, 6, 17)
    events = [
        _ev(date(2026, 6, 20), impact="medium", etype="CPI"),
        _ev(date(2026, 6, 20), impact="high", etype="FOMC"),
    ]
    out = nearest_gating_event(events, today, "US")
    assert out["impact"] == "high"


# ---------------------------------------------------------------------------
# confidence cap
# ---------------------------------------------------------------------------

def test_high_impact_caps():
    assert event_confidence_cap(1, "high") == 0.60
    assert event_confidence_cap(3, "high") == 0.75
    assert event_confidence_cap(7, "high") is None


def test_medium_impact_caps_only_imminent():
    assert event_confidence_cap(1, "medium") == 0.80
    assert event_confidence_cap(3, "medium") is None


def test_no_cap_on_missing_inputs():
    assert event_confidence_cap(None, "high") is None
    assert event_confidence_cap(2, None) is None


# ---------------------------------------------------------------------------
# engine wiring
# ---------------------------------------------------------------------------

def _strong():
    return [SignalResult("trend", 1.0, 1.0, 100.0, "strong_uptrend")]


def test_engine_applies_event_gate():
    capped = make_recommendation(_strong(), vol_20=0.2,
                                 event_context={"days_to_event": 1, "impact": "high"})
    free = make_recommendation(_strong(), vol_20=0.2)
    assert capped["confidence"] <= 0.60 < free["confidence"]
    assert capped["event_context"]["impact"] == "high"


def test_engine_no_gate_without_event():
    out = make_recommendation(_strong(), vol_20=0.2)
    assert out["event_context"] is None


def test_engine_event_gate_takes_lower_of_caps():
    # earnings gate 0.65 vs event gate 0.60 → most conservative wins
    out = make_recommendation(_strong(), vol_20=0.2, days_to_earnings=5,
                              event_context={"days_to_event": 1, "impact": "high"})
    assert out["confidence"] <= 0.60
