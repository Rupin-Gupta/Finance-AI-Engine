"""P9: market-data reliability — pure validation over stored OHLCV.

yfinance ships bad split adjustments, stale quotes, and occasional broken bars. These
checks surface them so the engine doesn't silently trade on garbage:
  - OHLC internal consistency (high≥low, high≥open/close, volume≥0)
  - return outliers (huge day-over-day jumps not explained by a known split/bonus)
  - staleness (latest bar older than tolerance, weekend-aware)
  - cross-source reconciliation (stored close vs a live quote)
India circuit-limit moves (±5/10/20%) are classified, not treated as data errors.
"""
from datetime import date, datetime, timedelta, timezone

# Day-over-day absolute return above this is suspicious unless a split explains it.
_OUTLIER_RETURN = 0.35
# Index-level circuit bands — a move landing on one is likely a circuit halt, not bad data,
# so it is classified separately (informational) and never counted as a quality issue. The 5%
# band is dropped: it is too common for single names to flag without false positives.
_CIRCUIT_BANDS = (0.10, 0.20)
_CIRCUIT_TOL = 0.015
# Stored close vs live quote disagreement beyond this fraction → reconciliation flag.
_RECONCILE_TOL = 0.02


def _as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)).date()
    except (ValueError, TypeError):
        return None


def check_ohlc_consistency(rows: list[dict]) -> list[dict]:
    """Bars that violate basic OHLC invariants."""
    bad = []
    for r in rows:
        o, h, l, c = r.get("open"), r.get("high"), r.get("low"), r.get("close")
        v = r.get("volume")
        if None in (o, h, l, c):
            continue
        o, h, l, c = float(o), float(h), float(l), float(c)
        reasons = []
        if h < l:
            reasons.append("high<low")
        if h < o or h < c:
            reasons.append("high<open/close")
        if l > o or l > c:
            reasons.append("low>open/close")
        if min(o, h, l, c) <= 0:
            reasons.append("non-positive price")
        if v is not None and float(v) < 0:
            reasons.append("negative volume")
        if reasons:
            bad.append({"date": str(_as_date(r.get("timestamp"))), "reasons": reasons})
    return bad


def detect_return_outliers(rows: list[dict], split_dates: set[str] | None = None) -> list[dict]:
    """Day-over-day return spikes beyond threshold, minus known split/circuit days."""
    split_dates = split_dates or set()
    out = []
    prev = None
    for r in rows:
        c = r.get("close")
        if c is None:
            continue
        c = float(c)
        if prev is not None and prev > 0:
            ret = (c - prev) / prev
            d = str(_as_date(r.get("timestamp")))
            if d not in split_dates:
                mag = abs(ret)
                if mag > _OUTLIER_RETURN:
                    # large unexplained jump → likely bad data
                    out.append({"date": d, "return": round(ret, 4), "classification": "outlier"})
                elif any(abs(mag - b) <= _CIRCUIT_TOL for b in _CIRCUIT_BANDS):
                    # lands on a circuit band → real market event, flagged informationally
                    out.append({"date": d, "return": round(ret, 4), "classification": "circuit_limit"})
        prev = c
    return out


def check_staleness(latest_ts, now: datetime | None = None, max_business_days: int = 4) -> dict:
    """Flag if the latest stored bar is older than tolerance (weekend-aware)."""
    now = now or datetime.now(tz=timezone.utc)
    latest = _as_date(latest_ts)
    if latest is None:
        return {"stale": True, "age_days": None, "latest": None}
    age = (now.date() - latest).days
    # subtract weekends in the gap (rough business-day age)
    business_age = age - 2 * (age // 7)
    return {"stale": business_age > max_business_days, "age_days": age, "latest": str(latest)}


def reconcile_quote(stored_close: float | None, live_close: float | None) -> dict | None:
    """Compare the latest stored close to a live quote; flag large disagreement."""
    if stored_close is None or live_close is None or stored_close <= 0:
        return None
    diff = abs(live_close - stored_close) / stored_close
    return {"stored": round(float(stored_close), 4), "live": round(float(live_close), 4),
            "diff_pct": round(diff, 4), "disagree": diff > _RECONCILE_TOL}


def assess_data_quality(rows: list[dict], split_dates: set[str] | None = None,
                        live_close: float | None = None, now: datetime | None = None) -> dict:
    """Full P9 report for one symbol's stored OHLCV (+ optional live quote)."""
    if not rows:
        return {"bars": 0, "ok": False, "issues": ["no stored data"]}

    consistency = check_ohlc_consistency(rows)
    outliers = detect_return_outliers(rows, split_dates)
    staleness = check_staleness(rows[-1].get("timestamp"), now)
    reconcile = reconcile_quote(float(rows[-1]["close"]) if rows[-1].get("close") is not None else None,
                                live_close)

    real_outliers = [o for o in outliers if o["classification"] == "outlier"]
    issues = []
    if consistency:
        issues.append(f"{len(consistency)} inconsistent bar(s)")
    if real_outliers:
        issues.append(f"{len(real_outliers)} return outlier(s)")
    if staleness["stale"]:
        issues.append(f"stale ({staleness['age_days']}d old)")
    if reconcile and reconcile["disagree"]:
        issues.append(f"live quote disagrees {reconcile['diff_pct']:.1%}")

    return {
        "bars": len(rows),
        "ok": not issues,
        "issues": issues,
        "consistency_violations": consistency,
        "outliers": outliers,
        "staleness": staleness,
        "reconciliation": reconcile,
    }
