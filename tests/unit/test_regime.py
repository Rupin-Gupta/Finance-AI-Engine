"""R5 market regime: pure classification, weight tilts, engine cap, job paths."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.analytics.regime import (
    REGIME_BULL, REGIME_BEAR, REGIME_HIGH_VOL, REGIME_SIDEWAYS,
    HIGH_VOL_CONF_CAP,
    classify_regime, compute_regime_features, regime_adjusted_weights,
    market_for_symbol,
)
from backend.decision.signals import SIGNAL_WEIGHTS, SignalResult
from backend.decision.engine import make_recommendation


# ---------------------------------------------------------------------------
# classify_regime
# ---------------------------------------------------------------------------

def test_high_vix_dominates_even_in_uptrend():
    out = classify_regime(110, 100, 90, vix=35.0)
    assert out["regime"] == REGIME_HIGH_VOL


def test_high_realized_vol_triggers_high_vol_when_vix_missing():
    out = classify_regime(110, 100, 90, vix=None, realized_vol=0.45)
    assert out["regime"] == REGIME_HIGH_VOL


def test_bull_when_above_both_smas():
    out = classify_regime(110, 100, 90, vix=15.0, realized_vol=0.10)
    assert out["regime"] == REGIME_BULL


def test_bear_when_below_both_smas():
    out = classify_regime(80, 100, 90, vix=15.0, realized_vol=0.10)
    assert out["regime"] == REGIME_BEAR


def test_mixed_trend_is_sideways():
    # above SMA50, below SMA200
    out = classify_regime(95, 90, 100, vix=15.0)
    assert out["regime"] == REGIME_SIDEWAYS


def test_weak_breadth_demotes_bull_to_sideways():
    out = classify_regime(110, 100, 90, vix=15.0, breadth_pct=0.30)
    assert out["regime"] == REGIME_SIDEWAYS


def test_strong_breadth_demotes_bear_to_sideways():
    out = classify_regime(80, 100, 90, vix=15.0, breadth_pct=0.70)
    assert out["regime"] == REGIME_SIDEWAYS


def test_missing_index_history_is_sideways():
    out = classify_regime(None, None, None)
    assert out["regime"] == REGIME_SIDEWAYS


def test_no_sma200_leans_on_sma50():
    out = classify_regime(110, 100, None, vix=15.0)
    assert out["regime"] == REGIME_BULL


# ---------------------------------------------------------------------------
# compute_regime_features
# ---------------------------------------------------------------------------

def test_features_from_long_series():
    closes = [100 + i * 0.1 for i in range(250)]
    f = compute_regime_features(closes)
    assert f["index_close"] == pytest.approx(closes[-1])
    assert f["sma_50"] == pytest.approx(sum(closes[-50:]) / 50)
    assert f["sma_200"] == pytest.approx(sum(closes[-200:]) / 200)
    assert f["realized_vol"] is not None and f["realized_vol"] >= 0


def test_features_short_series_graceful():
    f = compute_regime_features([100.0, 101.0])
    assert f["index_close"] == 101.0
    assert f["sma_50"] is None
    assert f["sma_200"] is None
    assert f["realized_vol"] is None


def test_features_empty_series():
    f = compute_regime_features([])
    assert f["index_close"] is None


# ---------------------------------------------------------------------------
# regime_adjusted_weights
# ---------------------------------------------------------------------------

def test_tilted_weights_preserve_sum():
    for regime in (REGIME_BULL, REGIME_BEAR, REGIME_SIDEWAYS, REGIME_HIGH_VOL):
        tilted = regime_adjusted_weights(SIGNAL_WEIGHTS, regime)
        assert sum(tilted.values()) == pytest.approx(sum(SIGNAL_WEIGHTS.values()))
        assert set(tilted) == set(SIGNAL_WEIGHTS)


def test_bull_tilts_momentum_up_rsi_down():
    tilted = regime_adjusted_weights(SIGNAL_WEIGHTS, REGIME_BULL)
    assert tilted["momentum"] > SIGNAL_WEIGHTS["momentum"]
    assert tilted["rsi"] < SIGNAL_WEIGHTS["rsi"]


def test_sideways_tilts_rsi_up_momentum_down():
    tilted = regime_adjusted_weights(SIGNAL_WEIGHTS, REGIME_SIDEWAYS)
    assert tilted["rsi"] > SIGNAL_WEIGHTS["rsi"]
    assert tilted["momentum"] < SIGNAL_WEIGHTS["momentum"]


def test_none_or_unknown_regime_returns_base_unchanged():
    assert regime_adjusted_weights(SIGNAL_WEIGHTS, None) == SIGNAL_WEIGHTS
    assert regime_adjusted_weights(SIGNAL_WEIGHTS, "weird") == SIGNAL_WEIGHTS


def test_empty_base_returns_empty():
    assert regime_adjusted_weights({}, REGIME_BULL) == {}


# ---------------------------------------------------------------------------
# engine regime cap
# ---------------------------------------------------------------------------

def _strong_signal() -> list[SignalResult]:
    return [SignalResult("trend", 1.0, 1.0, 100.0, "strong_uptrend")]


def test_high_vol_regime_caps_confidence():
    result = make_recommendation(_strong_signal(), vol_20=0.20, regime=REGIME_HIGH_VOL)
    assert result["confidence"] <= HIGH_VOL_CONF_CAP
    assert result["regime"] == REGIME_HIGH_VOL


def test_other_regimes_do_not_cap():
    capped = make_recommendation(_strong_signal(), vol_20=0.20, regime=REGIME_HIGH_VOL)
    free = make_recommendation(_strong_signal(), vol_20=0.20, regime=REGIME_BULL)
    assert free["confidence"] > capped["confidence"]
    none_regime = make_recommendation(_strong_signal(), vol_20=0.20)
    assert none_regime["regime"] is None


# ---------------------------------------------------------------------------
# market_for_symbol
# ---------------------------------------------------------------------------

def test_market_for_symbol():
    assert market_for_symbol("AAPL") == "US"
    assert market_for_symbol("RELIANCE.NS") == "INDIA"
    assert market_for_symbol("RELIANCE.BO") == "INDIA"


# ---------------------------------------------------------------------------
# regime_run job
# ---------------------------------------------------------------------------

def _make_conn():
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"id": "regime-job-1"})
    conn.execute = AsyncMock()
    return conn


def _make_pool(conn):
    pool = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=ctx)
    return pool


def _fake_ohlcv(symbol, period="1y", interval="1d"):
    closes = [100 + i * 0.1 for i in range(250)]
    return [{"close": c} for c in closes]


@pytest.mark.asyncio
async def test_regime_run_classifies_both_markets_and_completes():
    conn = _make_conn()
    pool = _make_pool(conn)
    upserted = []

    async def _capture_upsert(c, row):
        upserted.append(row)

    with patch("backend.scheduler.jobs.regime_run.get_db_pool", MagicMock(return_value=pool)), \
         patch("backend.scheduler.jobs.regime_run.create_job", AsyncMock(return_value="regime-job-1")), \
         patch("backend.scheduler.jobs.regime_run.update_job_status", AsyncMock()) as mock_update, \
         patch("backend.scheduler.jobs.regime_run.fetch_ohlcv", AsyncMock(side_effect=_fake_ohlcv)), \
         patch("backend.scheduler.jobs.regime_run.get_market_breadth", AsyncMock(return_value=0.6)), \
         patch("backend.scheduler.jobs.regime_run.upsert_regime", AsyncMock(side_effect=_capture_upsert)):
        from backend.scheduler.jobs.regime_run import _run
        await _run()

    markets = {r["market"] for r in upserted}
    assert markets == {"US", "INDIA"}
    for r in upserted:
        assert r["regime"] in (REGIME_BULL, REGIME_BEAR, REGIME_HIGH_VOL, REGIME_SIDEWAYS)
    mock_update.assert_awaited_once_with(conn, "regime-job-1", "completed")


@pytest.mark.asyncio
async def test_regime_run_marks_failed_when_all_markets_fail():
    conn = _make_conn()
    pool = _make_pool(conn)

    with patch("backend.scheduler.jobs.regime_run.get_db_pool", MagicMock(return_value=pool)), \
         patch("backend.scheduler.jobs.regime_run.create_job", AsyncMock(return_value="regime-job-2")), \
         patch("backend.scheduler.jobs.regime_run.update_job_status", AsyncMock()) as mock_update, \
         patch("backend.scheduler.jobs.regime_run.fetch_ohlcv", AsyncMock(side_effect=Exception("yf down"))):
        from backend.scheduler.jobs.regime_run import _run
        with pytest.raises(RuntimeError, match="regime_run failed"):
            await _run()

    args = mock_update.await_args.args
    assert args[2] == "failed"
