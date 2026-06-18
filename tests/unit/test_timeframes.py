"""P8 multi-timeframe: resample, per-timeframe summary, confluence."""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from backend.analytics.timeframes import (
    confluence, multi_timeframe_view, resample_ohlcv, summarize_timeframe, _ohlcv_frame,
)


def _daily_rows(n=400, start=100.0, drift=0.3):
    """Synthetic uptrending daily OHLCV rows."""
    base = datetime(2024, 1, 1)
    rows = []
    price = start
    for i in range(n):
        price += drift
        rows.append({
            "timestamp": base + timedelta(days=i),
            "open": price - 0.5, "high": price + 1.0, "low": price - 1.0,
            "close": price, "volume": 1_000_000 + i * 10,
        })
    return rows


# ---------------------------------------------------------------------------
# resample
# ---------------------------------------------------------------------------

def test_resample_weekly_aggregates():
    df = _ohlcv_frame(_daily_rows(70))
    wk = resample_ohlcv(df, "W-FRI")
    assert len(wk) < len(df)            # coarser
    assert set(["open", "high", "low", "close", "volume"]).issubset(wk.columns)
    # weekly high is the max of its daily highs
    assert wk["high"].iloc[0] >= wk["open"].iloc[0]


def test_resample_monthly_fewer_bars_than_weekly():
    df = _ohlcv_frame(_daily_rows(365))
    wk = resample_ohlcv(df, "W-FRI")
    mo = resample_ohlcv(df, "ME")
    assert len(mo) < len(wk) < len(df)


# ---------------------------------------------------------------------------
# summarize_timeframe
# ---------------------------------------------------------------------------

def test_summarize_uptrend_is_buy():
    df = _ohlcv_frame(_daily_rows(120, drift=0.5))
    out = summarize_timeframe(df, "daily", sentiment_score=0.3)
    assert out["timeframe"] == "daily"
    assert out["recommendation"] in ("BUY", "SELL", "HOLD")
    assert out["recommendation"] == "BUY"   # strong steady uptrend
    assert out["bars"] == 120


def test_summarize_none_on_thin_frame():
    df = _ohlcv_frame(_daily_rows(10))
    assert summarize_timeframe(df, "daily") is None


# ---------------------------------------------------------------------------
# confluence
# ---------------------------------------------------------------------------

def test_confluence_all_agree_is_strong():
    sums = [{"recommendation": "BUY"}, {"recommendation": "BUY"}, {"recommendation": "BUY"}]
    out = confluence(sums)
    assert out["aligned"] is True
    assert out["verdict"] == "STRONG_BUY"
    assert out["agreement"] == 1.0


def test_confluence_majority_leans():
    sums = [{"recommendation": "BUY"}, {"recommendation": "BUY"}, {"recommendation": "HOLD"}]
    out = confluence(sums)
    assert out["aligned"] is False
    assert out["verdict"] == "LEANS_BUY"
    assert out["agreement"] == pytest.approx(2 / 3, abs=1e-3)


def test_confluence_split_is_mixed():
    sums = [{"recommendation": "BUY"}, {"recommendation": "SELL"},
            {"recommendation": "HOLD"}, {"recommendation": "SELL"}]
    out = confluence(sums)
    assert out["verdict"] in ("MIXED", "LEANS_SELL")


def test_confluence_empty():
    out = confluence([])
    assert out["verdict"] == "INSUFFICIENT"
    assert out["aligned"] is None


# ---------------------------------------------------------------------------
# multi_timeframe_view
# ---------------------------------------------------------------------------

def test_multi_timeframe_view_daily_weekly_present():
    out = multi_timeframe_view(_daily_rows(400, drift=0.4), sentiment_score=0.2)
    tfs = {s["timeframe"] for s in out["timeframes"]}
    assert "daily" in tfs
    assert "weekly" in tfs          # 400 days → ~57 weeks ≥ 25
    assert "confluence" in out
    assert out["confluence"]["counts"]


def test_multi_timeframe_view_empty_daily():
    out = multi_timeframe_view([], sentiment_score=None)
    assert out["timeframes"] == []
    assert out["confluence"]["verdict"] == "INSUFFICIENT"
