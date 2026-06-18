"""R6 portfolio risk: pure analytics over synthetic positions + prices."""
import numpy as np
import pandas as pd
import pytest

from backend.analytics.portfolio_risk import (
    assess_portfolio_risk,
    build_warnings,
    correlation_metrics,
    country_exposure,
    market_cap_exposure,
    position_weights,
    risk_score,
    sector_exposure,
    var_cvar,
)


def _positions():
    return [
        {"symbol": "AAPL", "value": 5000.0},
        {"symbol": "MSFT", "value": 3000.0},
        {"symbol": "RELIANCE.NS", "value": 2000.0},
    ]


def _prices(n_days=120, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=n_days, freq="B")
    base = rng.normal(0.0005, 0.015, size=n_days).cumsum()
    cols = {}
    for i, sym in enumerate(("AAPL", "MSFT", "RELIANCE.NS")):
        noise = rng.normal(0, 0.01, size=n_days).cumsum()
        cols[sym] = 100 * np.exp(base + noise * (i + 1) * 0.5)
    return pd.DataFrame(cols, index=dates)


# ---------------------------------------------------------------------------
# weights / exposures
# ---------------------------------------------------------------------------

def test_position_weights_sum_to_one():
    w = position_weights(_positions())
    assert sum(w.values()) == pytest.approx(1.0)
    assert w["AAPL"] == pytest.approx(0.5)


def test_position_weights_empty_on_zero_value():
    assert position_weights([{"symbol": "A", "value": 0}]) == {}


def test_sector_exposure_with_unknowns():
    out = sector_exposure(_positions(), {"AAPL": "Technology", "MSFT": "Technology"})
    assert out["by_sector"]["Technology"] == pytest.approx(0.8)
    assert out["by_sector"]["Unknown"] == pytest.approx(0.2)
    assert out["top_sector"] == "Technology"
    assert 0 < out["hhi"] <= 1


def test_country_exposure_suffix_split():
    out = country_exposure(_positions())
    assert out["INDIA"] == pytest.approx(0.2)
    assert out["US"] == pytest.approx(0.8)


def test_market_cap_buckets():
    caps = {"AAPL": 3e12, "MSFT": 5e9, "RELIANCE.NS": None}
    out = market_cap_exposure(_positions(), caps)
    assert out["large"] == pytest.approx(0.5)
    assert out["mid"] == pytest.approx(0.3)
    assert out["unknown"] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# correlation / VaR
# ---------------------------------------------------------------------------

def test_correlation_metrics_shape():
    w = position_weights(_positions())
    out = correlation_metrics(_prices(), w)
    assert out is not None
    assert -1 <= out["avg_pairwise"] <= 1
    assert set(out["max_pair"]["symbols"]) <= {"AAPL", "MSFT", "RELIANCE.NS"}


def test_correlation_none_when_single_symbol():
    assert correlation_metrics(_prices()[["AAPL"]], {"AAPL": 1.0}) is None


def test_var_cvar_ordering_and_scale():
    w = position_weights(_positions())
    out = var_cvar(_prices(), w, total_value=10_000.0)
    assert out is not None
    assert out["cvar_pct"] >= out["var_pct"] >= 0
    assert out["var_value"] == pytest.approx(out["var_pct"] * 10_000, rel=1e-6)
    assert out["annualized_vol"] > 0


def test_var_none_on_short_history():
    w = position_weights(_positions())
    assert var_cvar(_prices(n_days=10), w, 10_000.0) is None


def test_perfectly_correlated_assets_high_corr():
    dates = pd.date_range("2025-01-01", periods=100, freq="B")
    series = pd.Series(np.linspace(100, 150, 100) + np.sin(np.arange(100)), index=dates)
    prices = pd.DataFrame({"A": series, "B": series * 2})
    out = correlation_metrics(prices, {"A": 0.5, "B": 0.5})
    assert out["avg_pairwise"] == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# score + warnings
# ---------------------------------------------------------------------------

def test_risk_score_levels():
    concentrated = {"hhi": 1.0, "top_sector": "Tech", "top_sector_pct": 1.0}
    out = risk_score(concentrated, {"avg_pairwise": 0.9, "max_pair": {}},
                     {"annualized_vol": 0.5, "var_pct": 0.05, "cvar_pct": 0.07,
                      "confidence": 0.95})
    assert out["level"] == "Extreme"
    spread = {"hhi": 0.1, "top_sector": "Tech", "top_sector_pct": 0.2}
    out2 = risk_score(spread, {"avg_pairwise": 0.1, "max_pair": {}},
                      {"annualized_vol": 0.08, "var_pct": 0.005, "cvar_pct": 0.008,
                       "confidence": 0.95})
    assert out2["level"] == "Low"
    assert out["score"] > out2["score"]


def test_warnings_fire_on_concentration():
    positions = [{"symbol": "AAPL", "value": 9000.0}, {"symbol": "MSFT", "value": 1000.0}]
    sector = sector_exposure(positions, {"AAPL": "Technology", "MSFT": "Technology"})
    warnings = build_warnings(positions, sector, None, None)
    assert any("Technology" in w for w in warnings)          # sector >40%
    assert any("AAPL" in w and "90%" in w for w in warnings)  # single position >25%


def test_no_warnings_for_balanced_portfolio():
    positions = [{"symbol": s, "value": 1000.0} for s in ("A", "B", "C", "D", "E")]
    sector_map = {s: f"S{i}" for i, s in enumerate(("A", "B", "C", "D", "E"))}
    warnings = build_warnings(positions, sector_exposure(positions, sector_map), None, None)
    assert warnings == []


# ---------------------------------------------------------------------------
# full report
# ---------------------------------------------------------------------------

def test_assess_full_report():
    out = assess_portfolio_risk(
        _positions(),
        {"AAPL": "Technology", "MSFT": "Technology", "RELIANCE.NS": "Energy"},
        {"AAPL": 3e12, "MSFT": 3e12, "RELIANCE.NS": 2e13},
        _prices(),
    )
    assert out["positions"] == 3
    assert out["total_value"] == pytest.approx(10_000.0)
    assert out["risk_score"]["level"] in ("Low", "Medium", "High", "Extreme")
    assert out["var"] is not None
    assert out["correlation"] is not None
    assert sum(out["weights"].values()) == pytest.approx(1.0)


def test_assess_graceful_without_prices():
    out = assess_portfolio_risk(_positions(), {}, {}, pd.DataFrame())
    assert out["var"] is None
    assert out["correlation"] is None
    assert out["risk_score"]["level"]  # still scored on concentration alone


def test_assess_empty_positions():
    out = assess_portfolio_risk([], {}, {}, pd.DataFrame())
    assert out["positions"] == 0
