"""P3 stop-loss / trailing-stop: pure stop logic + vol sizing + breach detection."""
import math

import pytest

from backend.analytics.stops import (
    DEFAULT_STOP_PCT, _MAX_STOP_PCT, _MIN_STOP_PCT,
    evaluate_stop, position_stop, recommended_stop_pct, stop_level,
)


# ---------------------------------------------------------------------------
# recommended_stop_pct
# ---------------------------------------------------------------------------

def test_recommended_clamped_to_bounds():
    assert recommended_stop_pct(0.01, "Low") == _MIN_STOP_PCT     # tiny vol → floor
    assert recommended_stop_pct(5.0, "Extreme") == _MAX_STOP_PCT  # huge vol → cap


def test_recommended_scales_with_vol():
    lo = recommended_stop_pct(0.20, "Medium")
    hi = recommended_stop_pct(0.45, "Medium")
    assert hi > lo
    # ~3 daily sigma
    assert lo == pytest.approx(min(max(0.20 / math.sqrt(252) * 3.0, _MIN_STOP_PCT), _MAX_STOP_PCT), abs=1e-4)


def test_recommended_risk_level_widens():
    base = recommended_stop_pct(0.35, "Low")
    extreme = recommended_stop_pct(0.35, "Extreme")
    assert extreme >= base


def test_recommended_defaults_without_vol():
    assert recommended_stop_pct(None, None) == pytest.approx(DEFAULT_STOP_PCT)


# ---------------------------------------------------------------------------
# stop_level
# ---------------------------------------------------------------------------

def test_fixed_stop_from_entry():
    assert stop_level(100.0, high_water=130.0, stop_pct=0.10, trailing=False) == 90.0


def test_trailing_stop_ratchets_from_high_water():
    assert stop_level(100.0, high_water=130.0, stop_pct=0.10, trailing=True) == 117.0


def test_trailing_never_below_entry_stop():
    # high-water below entry (underwater) → reference stays at entry
    assert stop_level(100.0, high_water=90.0, stop_pct=0.10, trailing=True) == 90.0


# ---------------------------------------------------------------------------
# evaluate_stop
# ---------------------------------------------------------------------------

def test_evaluate_breached():
    ev = evaluate_stop(100.0, current=88.0, high_water=100.0, stop_pct=0.10, trailing=False)
    assert ev["breached"] is True
    assert ev["stop_level"] == 90.0
    assert ev["distance_pct"] < 0


def test_evaluate_not_breached_with_locked_gain():
    ev = evaluate_stop(100.0, current=125.0, high_water=130.0, stop_pct=0.10, trailing=True)
    assert ev["breached"] is False
    assert ev["stop_level"] == 117.0
    assert ev["stop_pl_pct"] == pytest.approx(0.17)  # trailing locked +17%
    assert ev["distance_pct"] == pytest.approx((125.0 - 117.0) / 125.0, abs=1e-4)


def test_evaluate_none_without_entry_or_price():
    assert evaluate_stop(None, 100.0, 100.0, 0.1, True) is None
    assert evaluate_stop(100.0, None, 100.0, 0.1, True) is None
    assert evaluate_stop(0.0, 100.0, 100.0, 0.1, True) is None


# ---------------------------------------------------------------------------
# position_stop orchestrator
# ---------------------------------------------------------------------------

def test_position_stop_uses_recommended_when_no_override():
    out = position_stop(entry=100.0, current=95.0, high_water=110.0,
                        vol_20=0.30, risk_level="Medium")
    assert out["recommended"] is True
    assert out["stop_pct"] == recommended_stop_pct(0.30, "Medium")


def test_position_stop_respects_override():
    out = position_stop(entry=100.0, current=95.0, high_water=110.0,
                        vol_20=0.30, risk_level="Medium", stop_pct=0.05, trailing=False)
    assert out["recommended"] is False
    assert out["stop_pct"] == 0.05
    assert out["stop_level"] == 95.0  # fixed: 100 * 0.95


def test_position_stop_none_without_entry():
    assert position_stop(entry=None, current=95.0, high_water=110.0) is None
