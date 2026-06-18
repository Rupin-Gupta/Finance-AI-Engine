"""P9 data reliability: OHLC consistency, outliers, staleness, reconciliation."""
from datetime import datetime, timedelta, timezone

import pytest

from backend.analytics.data_quality import (
    assess_data_quality, check_ohlc_consistency, check_staleness,
    detect_return_outliers, reconcile_quote,
)


def _bar(ts, o, h, l, c, v=1_000_000):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _series(closes, start=datetime(2026, 1, 1, tzinfo=timezone.utc)):
    return [_bar(start + timedelta(days=i), c, c + 1, c - 1, c) for i, c in enumerate(closes)]


# ---------------------------------------------------------------------------
# OHLC consistency
# ---------------------------------------------------------------------------

def test_consistency_flags_high_below_low():
    rows = [_bar(datetime(2026, 1, 1), 100, 95, 99, 98)]  # high<low, high<open
    bad = check_ohlc_consistency(rows)
    assert len(bad) == 1
    assert "high<low" in bad[0]["reasons"]


def test_consistency_flags_negative_volume_and_price():
    rows = [_bar(datetime(2026, 1, 1), 100, 101, 99, 100, v=-5),
            _bar(datetime(2026, 1, 2), 0, 1, -1, 0)]
    bad = check_ohlc_consistency(rows)
    assert len(bad) == 2


def test_consistency_clean_bars_pass():
    assert check_ohlc_consistency(_series([100, 101, 102])) == []


# ---------------------------------------------------------------------------
# outliers
# ---------------------------------------------------------------------------

def test_outlier_detected():
    rows = _series([100, 101, 160, 161])  # +58% jump
    out = detect_return_outliers(rows)
    assert any(o["classification"] == "outlier" for o in out)


def test_outlier_suppressed_on_split_date():
    rows = _series([100, 101, 50, 51])    # -50% looks like a 2:1 split
    split_day = str((datetime(2026, 1, 1) + timedelta(days=2)).date())
    out = detect_return_outliers(rows, split_dates={split_day})
    assert out == []


def test_big_unexplained_jump_is_outlier():
    rows = _series([100, 100, 60])        # -40% → above the 0.35 gate
    out = detect_return_outliers(rows)
    assert out and out[0]["classification"] == "outlier"


def test_circuit_band_move_classified_circuit_not_issue():
    # ~-20% lands on a circuit band → circuit_limit (informational), NOT a data outlier.
    rows = _series([100, 100, 80])        # -20%
    out = detect_return_outliers(rows)
    assert out and out[0]["classification"] == "circuit_limit"
    # a -10% move is also a circuit band, not an outlier
    out10 = detect_return_outliers(_series([100, 100, 90]))
    assert out10 and out10[0]["classification"] == "circuit_limit"
    # and circuit classifications do not flip a series to "not ok"
    report = assess_data_quality(_series([100, 100, 80],
                                         start=datetime.now(timezone.utc) - timedelta(days=3)))
    assert all(o["classification"] == "circuit_limit" for o in report["outliers"])
    # the only issue here would be staleness/recon, not the circuit move itself
    assert "return outlier" not in " ".join(report["issues"])


# ---------------------------------------------------------------------------
# staleness
# ---------------------------------------------------------------------------

def test_staleness_fresh():
    now = datetime(2026, 6, 17, tzinfo=timezone.utc)
    out = check_staleness(datetime(2026, 6, 16, tzinfo=timezone.utc), now=now)
    assert out["stale"] is False
    assert out["age_days"] == 1


def test_staleness_old():
    now = datetime(2026, 6, 17, tzinfo=timezone.utc)
    out = check_staleness(datetime(2026, 5, 1, tzinfo=timezone.utc), now=now)
    assert out["stale"] is True


def test_staleness_none_ts():
    assert check_staleness(None)["stale"] is True


# ---------------------------------------------------------------------------
# reconciliation
# ---------------------------------------------------------------------------

def test_reconcile_agree_and_disagree():
    assert reconcile_quote(100.0, 100.5)["disagree"] is False
    assert reconcile_quote(100.0, 105.0)["disagree"] is True


def test_reconcile_none_inputs():
    assert reconcile_quote(None, 100.0) is None
    assert reconcile_quote(100.0, None) is None


# ---------------------------------------------------------------------------
# full report
# ---------------------------------------------------------------------------

def test_assess_clean_series_ok():
    rows = _series([100 + i for i in range(30)],
                   start=datetime.now(timezone.utc) - timedelta(days=30))
    out = assess_data_quality(rows)
    assert out["ok"] is True
    assert out["issues"] == []


def test_assess_dirty_series_flags_issues():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = _series([100, 180, 181], start=base)        # +80% outlier + very stale
    rows.append(_bar(base + timedelta(days=3), 100, 95, 99, 98))  # inconsistent bar
    out = assess_data_quality(rows, now=datetime(2026, 6, 17, tzinfo=timezone.utc))
    assert out["ok"] is False
    assert len(out["issues"]) >= 2


def test_assess_empty():
    out = assess_data_quality([])
    assert out["ok"] is False
    assert out["bars"] == 0


# ---------------------------------------------------------------------------
# regression: NULL count-weighted sentiment score must not crash the aggregate
# (recurrence of the float(None) class of bug — see SPEC B23/B27)
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, *_a, **_k):
        return self._rows


def test_get_sentiment_by_date_range_skips_null_score():
    import asyncio
    from datetime import date as _date
    from backend.db.queries.sentiment import get_sentiment_by_date_range

    rows = [{"date": _date(2026, 6, 1), "score": None},
            {"date": _date(2026, 6, 2), "score": 0.4}]
    out = asyncio.run(get_sentiment_by_date_range(_FakeConn(rows), "AAPL", _date(2026, 6, 1), _date(2026, 6, 2)))
    assert out == {_date(2026, 6, 2): 0.4}   # NULL row dropped, not crashed
