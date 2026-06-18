"""R7: model drift monitoring — pure functions over scored decisions + signal history.

Tracks whether the engine's accuracy is decaying over time (concept/prediction drift)
and whether individual signals are losing their edge. Consumed by the calibration
router ("Model Health" panel) and by signal_snapshot_run (drift alerts).

Verdicts:
  insufficient_data — not enough scored history to judge
  healthy           — recent hit rate within tolerance of baseline
  degrading         — recent hit rate > 5pp below baseline
  retraining_recommended — recent hit rate > 10pp below baseline
"""
from datetime import date, timedelta

_DEGRADING_DELTA = -0.05
_RETRAIN_DELTA = -0.10
_MIN_WINDOW_COUNT = 10

VERDICT_INSUFFICIENT = "insufficient_data"
VERDICT_HEALTHY = "healthy"
VERDICT_DEGRADING = "degrading"
VERDICT_RETRAIN = "retraining_recommended"


def _row_date(row: dict) -> date | None:
    raw = row.get("decision_date")
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def rolling_hit_rate(scored: list[dict], window_days: int = 30, step_days: int = 7) -> list[dict]:
    """Hit-rate time series over trailing windows (oldest → newest)."""
    dated = [(d, r) for r in scored if (d := _row_date(r)) is not None]
    if not dated:
        return []
    first = min(d for d, _ in dated)
    last = max(d for d, _ in dated)
    out = []
    end = first + timedelta(days=window_days)
    while end <= last + timedelta(days=step_days):
        start = end - timedelta(days=window_days)
        window = [r for d, r in dated if start <= d < end]
        if window:
            out.append({
                "window_end": str(min(end, last)),
                "count": len(window),
                "hit_rate": round(sum(1 for r in window if r["correct"]) / len(window), 4),
            })
        end += timedelta(days=step_days)
    return out


def drift_verdict(scored: list[dict], recent_days: int = 30, baseline_days: int = 90) -> dict:
    """Compare the recent window's hit rate to the preceding baseline window."""
    dated = [(d, r) for r in scored if (d := _row_date(r)) is not None]
    if not dated:
        return {"status": VERDICT_INSUFFICIENT, "recent": None, "baseline": None, "delta": None}

    last = max(d for d, _ in dated)
    recent_start = last - timedelta(days=recent_days)
    baseline_start = recent_start - timedelta(days=baseline_days)

    recent = [r for d, r in dated if d > recent_start]
    baseline = [r for d, r in dated if baseline_start < d <= recent_start]

    if len(recent) < _MIN_WINDOW_COUNT or len(baseline) < _MIN_WINDOW_COUNT:
        return {"status": VERDICT_INSUFFICIENT,
                "recent": _window_stats(recent), "baseline": _window_stats(baseline), "delta": None}

    r_hit = sum(1 for r in recent if r["correct"]) / len(recent)
    b_hit = sum(1 for r in baseline if r["correct"]) / len(baseline)
    delta = round(r_hit - b_hit, 4)

    if delta <= _RETRAIN_DELTA:
        status = VERDICT_RETRAIN
    elif delta <= _DEGRADING_DELTA:
        status = VERDICT_DEGRADING
    else:
        status = VERDICT_HEALTHY
    return {"status": status,
            "recent": _window_stats(recent), "baseline": _window_stats(baseline), "delta": delta}


def _window_stats(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    return {"count": len(rows),
            "hit_rate": round(sum(1 for r in rows if r["correct"]) / len(rows), 4)}


def signal_drift(history: list[dict]) -> list[dict]:
    """Per-signal accuracy trend from signal_performance snapshots.

    history rows: {snapshot_date, signal, accuracy} (any order). Slope is a simple
    least-squares fit of accuracy vs snapshot index — sign matters more than scale.
    """
    by_signal: dict[str, list[tuple]] = {}
    for r in history:
        if r.get("accuracy") is None:
            continue
        by_signal.setdefault(r["signal"], []).append((str(r["snapshot_date"]), float(r["accuracy"])))

    out = []
    for name, points in by_signal.items():
        points.sort(key=lambda p: p[0])
        ys = [p[1] for p in points]
        n = len(ys)
        if n < 2:
            slope = 0.0
        else:
            xs = list(range(n))
            mx, my = sum(xs) / n, sum(ys) / n
            denom = sum((x - mx) ** 2 for x in xs)
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom if denom else 0.0
        trend = "declining" if slope < -0.01 else "improving" if slope > 0.01 else "stable"
        out.append({
            "signal": name,
            "snapshots": n,
            "first_accuracy": round(ys[0], 4),
            "last_accuracy": round(ys[-1], 4),
            "slope": round(slope, 4),
            "trend": trend,
        })
    out.sort(key=lambda s: s["slope"])
    return out


def model_health(scored: list[dict], history: list[dict],
                 window_days: int = 30, step_days: int = 7) -> dict:
    """Full R7 report: rolling accuracy + drift verdict + per-signal trend."""
    verdict = drift_verdict(scored)
    declining = [s["signal"] for s in signal_drift(history) if s["trend"] == "declining"]
    return {
        "verdict": verdict["status"],
        "drift": verdict,
        "rolling": rolling_hit_rate(scored, window_days, step_days),
        "signal_drift": signal_drift(history),
        "declining_signals": declining,
    }
