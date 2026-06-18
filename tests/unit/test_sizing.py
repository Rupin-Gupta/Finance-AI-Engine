"""Position sizing: Kelly / vol-target / risk-budget → conservative recommendation."""
from backend.analytics.sizing import recommend_size


def test_high_confidence_low_risk_hits_risk_budget_cap():
    s = recommend_size(confidence=0.8, vol_annualized=0.25, risk_level="Low")
    # kelly(½)=0.3, vol_target=0.6, risk_budget=0.20 → min 0.20; Low risk ×1.0
    assert s["recommended_pct"] == 0.20
    assert s["win_prob"] == 0.8
    assert "risk budget" in s["reason"]


def test_kelly_binds_when_confidence_modest():
    s = recommend_size(confidence=0.6, vol_annualized=0.25, risk_level="Low")
    # kelly_full=0.2 → half=0.1; that's the min
    assert s["recommended_pct"] == 0.1
    assert "Kelly" in s["reason"]


def test_no_edge_recommends_flat():
    s = recommend_size(confidence=0.5, vol_annualized=0.25, risk_level="Low")
    assert s["recommended_pct"] == 0.0
    assert "No positive edge" in s["reason"]


def test_high_risk_multiplier_trims_size():
    s = recommend_size(confidence=0.6, vol_annualized=0.25, risk_level="High")
    assert s["risk_multiplier"] == 0.5
    assert s["recommended_pct"] == 0.05   # 0.1 * 0.5


def test_missing_vol_falls_back_to_caps():
    s = recommend_size(confidence=0.8, vol_annualized=None, risk_level="Low")
    assert s["stop_distance"] == 0.05
    assert s["recommended_pct"] == 0.20   # vol_target & risk_budget both cap at max


def test_win_prob_overrides_confidence():
    s = recommend_size(confidence=0.9, vol_annualized=0.25, risk_level="Low", win_prob=0.5)
    assert s["win_prob"] == 0.5
    assert s["recommended_pct"] == 0.0    # no edge despite high confidence


def test_recommended_never_exceeds_cap():
    s = recommend_size(confidence=0.99, vol_annualized=0.05, risk_level="Low", max_position=0.10)
    assert 0.0 <= s["recommended_pct"] <= 0.10
