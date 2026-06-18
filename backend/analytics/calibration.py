"""Confidence calibration + signal edge + threshold tuning — the ML feedback loop.

All functions are pure (no I/O) and operate on already-scored decision rows, each
carrying realized outcomes. The router resolves prices and feeds these.

Row fields expected (per function):
  reliability_curve  -> confidence (float), correct (bool)
  signal_contribution-> signals (dict name->{score,...}), realized_move (float)
  tune_thresholds    -> weighted_score (float), realized_move (float)
"""
import json
from datetime import timedelta

from backend.analytics.performance import HOLD_BAND, resolve_price, evaluate_decision
from backend.analytics.backtest import CostModel


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def parse_signals(raw) -> dict:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw or {}


def weighted_score_from_signals(signals: dict) -> float:
    return sum(
        (v.get("score") or 0.0) * (v.get("weight") or 0.0)
        for v in signals.values()
        if isinstance(v, dict)
    )


def score_for_calibration(decisions: list, closes_by_symbol: dict, horizon_days: int, today) -> list[dict]:
    """Resolve outcomes + attach signals/weighted_score/strategy_return per elapsed decision. Pure.

    Decisions whose horizon hasn't elapsed, or that lack price data, are skipped.
    """
    scored: list[dict] = []
    for d in decisions:
        series = closes_by_symbol.get(d["symbol"])
        if not series:
            continue
        created = d["created_at"]
        dec_date = created.date() if hasattr(created, "date") else created
        if dec_date + timedelta(days=horizon_days) > today:
            continue

        entry = resolve_price(series, dec_date, "on_or_before")
        exit_ = resolve_price(series, dec_date + timedelta(days=horizon_days), "on_or_after")
        ev = evaluate_decision(d["recommendation"], entry, exit_)
        if ev is None:
            continue

        signals = parse_signals(d["signals_json"])
        scored.append({
            "symbol": d["symbol"],
            "decision_date": str(dec_date),
            "recommendation": d["recommendation"],
            "risk_level": d["risk_level"],
            "confidence": float(d["confidence"]) if d["confidence"] is not None else None,
            "signals": signals,
            "weighted_score": round(weighted_score_from_signals(signals), 6),
            "realized_move": ev["realized_move"],
            "strategy_return": ev["strategy_return"],
            # Round-trip transaction cost for this symbol — lets the weight tuner score
            # net-of-cost (R4.1) without re-deriving the market per row.
            "cost_fraction": CostModel.for_symbol(d["symbol"]).round_trip_cost_fraction,
            "correct": ev["correct"],
        })
    return scored


# ---------------------------------------------------------------------------
# Reliability / calibration
# ---------------------------------------------------------------------------

def reliability_curve(rows: list[dict], n_bins: int = 10) -> dict:
    """Bin decisions by confidence; compare predicted confidence vs observed hit rate.

    Returns per-bin stats plus Brier score and Expected Calibration Error (ECE).
    A perfectly calibrated model has hit_rate == mean_confidence in every bin (ECE 0).
    """
    n = len(rows)
    if n == 0:
        return {"count": 0, "bins": [], "brier_score": None, "ece": None}

    buckets: list[list[dict]] = [[] for _ in range(n_bins)]
    for r in rows:
        conf = max(0.0, min(1.0, float(r["confidence"] if r["confidence"] is not None else 0.0)))
        idx = min(int(conf * n_bins), n_bins - 1)
        buckets[idx].append(r)

    bins = []
    ece = 0.0
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        cnt = len(bucket)
        mean_conf = sum(float(r["confidence"] or 0.0) for r in bucket) / cnt
        hit_rate = sum(1 for r in bucket if r["correct"]) / cnt
        ece += (cnt / n) * abs(hit_rate - mean_conf)
        bins.append({
            "bin_lower": round(i / n_bins, 2),
            "bin_upper": round((i + 1) / n_bins, 2),
            "count": cnt,
            "mean_confidence": round(mean_conf, 4),
            "hit_rate": round(hit_rate, 4),
            "gap": round(hit_rate - mean_conf, 4),
        })

    brier = sum((float(r["confidence"] or 0.0) - (1.0 if r["correct"] else 0.0)) ** 2 for r in rows) / n
    return {"count": n, "bins": bins, "brier_score": round(brier, 4), "ece": round(ece, 4)}


# ---------------------------------------------------------------------------
# Per-signal contribution / edge
# ---------------------------------------------------------------------------

def signal_contribution(rows: list[dict]) -> list[dict]:
    """Per signal: directional accuracy AND additive return attribution.

    accuracy = share of active calls where sign(score) == sign(realized_move).
    attribution = Σ over BUY/SELL decisions of (score·weight / weighted_score) · strategy_return.
      The shares sum to 1 per decision, so summing attributed_return across signals
      reconstructs the decision's strategy return — a clean additive decomposition of
      *which signals earned (or lost) the money*.
    """
    stats: dict[str, dict] = {}
    total_strategy_return = 0.0

    for r in rows:
        move_dir = _sign(r["realized_move"])
        if move_dir == 0:
            continue  # no directional outcome to attribute
        strat = r.get("strategy_return")
        weighted = r.get("weighted_score")
        if strat is not None:
            total_strategy_return += strat

        for name, sig in (r.get("signals") or {}).items():
            score = sig.get("score")
            if score is None or score == 0:
                continue
            s = stats.setdefault(name, {
                "active": 0, "correct": 0, "abs_score": 0.0, "weight": 0.0, "attributed": 0.0,
            })
            s["active"] += 1
            s["abs_score"] += abs(score)
            weight = float(sig.get("weight") or 0.0)
            s["weight"] += weight
            if move_dir != 0 and _sign(score) == move_dir:
                s["correct"] += 1
            # additive return attribution (only when the trade had a non-zero conviction)
            if strat is not None and weighted:
                s["attributed"] += (score * weight / weighted) * strat

    out = []
    for name, s in stats.items():
        if s["active"] == 0:
            continue
        attributed = round(s["attributed"], 6)
        out.append({
            "signal": name,
            "active_count": s["active"],
            "accuracy": round(s["correct"] / s["active"], 4),
            "avg_abs_score": round(s["abs_score"] / s["active"], 4),
            "avg_weight": round(s["weight"] / s["active"], 4),
            "attributed_return": attributed,
            "return_share": round(attributed / total_strategy_return, 4) if total_strategy_return else None,
        })
    out.sort(key=lambda x: x["accuracy"], reverse=True)
    return out


# ---------------------------------------------------------------------------
# Threshold tuning
# ---------------------------------------------------------------------------

def _eval_at_threshold(rows: list[dict], threshold: float) -> dict:
    trades = hits = 0
    total_return = 0.0
    for r in rows:
        w = r["weighted_score"]
        move = r["realized_move"]
        if w >= threshold:
            rec, strat = "BUY", move
        elif w <= -threshold:
            rec, strat = "SELL", -move
        else:
            rec, strat = "HOLD", 0.0
        total_return += strat
        if rec != "HOLD":
            trades += 1
            if (rec == "BUY" and move > 0) or (rec == "SELL" and move < 0):
                hits += 1
    n = len(rows)
    return {
        "threshold": round(threshold, 4),
        "trades": trades,
        "hit_rate": round(hits / trades, 4) if trades else None,
        "avg_return": round(total_return / n, 6) if n else None,
        "coverage": round(trades / n, 4) if n else None,
    }


def tune_thresholds(
    rows: list[dict],
    current_threshold: float = 0.30,
    grid: list[float] | None = None,
    min_trades: int = 5,
) -> dict:
    """Grid-search the BUY/SELL weighted-score threshold to maximize hit rate.

    Relabels every decision at each candidate threshold and re-scores against the
    realized move. Returns the grid, the current threshold's stats, and the best
    (highest hit rate with at least `min_trades`, tie-broken by more trades).
    """
    if not rows:
        return {"current": None, "grid": [], "best": None}

    if grid is None:
        grid = [round(0.10 + 0.05 * i, 2) for i in range(11)]  # 0.10 … 0.60

    curve = [_eval_at_threshold(rows, t) for t in grid]
    eligible = [c for c in curve if c["hit_rate"] is not None and c["trades"] >= min_trades]
    best = max(eligible, key=lambda c: (c["hit_rate"], c["trades"]), default=None)

    return {
        "current": _eval_at_threshold(rows, current_threshold),
        "current_threshold": current_threshold,
        "grid": curve,
        "best": best,
    }


# ---------------------------------------------------------------------------
# Calibrated win probability (R2.1) — feeds position sizing
# ---------------------------------------------------------------------------

def calibration_summary(scored: list[dict]) -> dict:
    """Compact, persistable calibration snapshot for cheap online reads.

    Bundles the reliability curve (confidence→hit-rate bins) with per-recommendation
    and overall hit rate. The decision endpoint reads this and maps a new call's
    confidence to a calibrated win probability instead of re-scoring all history.
    """
    rel = reliability_curve(scored)
    by_rec: dict[str, dict] = {}
    for rec in ("BUY", "SELL", "HOLD"):
        subset = [r for r in scored if r.get("recommendation") == rec]
        if subset:
            hits = sum(1 for r in subset if r["correct"])
            by_rec[rec] = {"count": len(subset), "hit_rate": round(hits / len(subset), 4)}
    n = len(scored)
    overall = round(sum(1 for r in scored if r["correct"]) / n, 4) if n else None
    return {
        "reliability": rel,
        "by_recommendation": by_rec,
        "overall_hit_rate": overall,
        "count": n,
    }


def lookup_calibrated_prob(
    bins: list[dict], confidence, min_count: int = 10, fallback=None
) -> float | None:
    """Map a confidence to the empirical hit rate of its reliability bin.

    With a thin bin (< min_count samples) we shrink toward the raw confidence
    (or `fallback`) proportionally to the sample size, so a single lucky bin can't
    swing sizing. Returns `fallback`/confidence when no history exists.
    """
    if confidence is None:
        return fallback
    fb = fallback if fallback is not None else confidence
    if not bins:
        return fb

    chosen = None
    for b in bins:
        lo, hi = b["bin_lower"], b["bin_upper"]
        if lo <= confidence < hi or (confidence >= hi >= 1.0):
            chosen = b
            break
    if chosen is None:  # confidence outside observed bins — take the nearest
        chosen = min(bins, key=lambda b: abs(b["mean_confidence"] - confidence))

    cnt, hit = chosen["count"], chosen["hit_rate"]
    if cnt >= min_count:
        return round(hit, 4)
    w = cnt / min_count
    return round(w * hit + (1 - w) * fb, 4)


# ---------------------------------------------------------------------------
# Per-call attribution (R9) — explain each closed call's realized return
# ---------------------------------------------------------------------------

def decompose_decision(row: dict) -> list[dict]:
    """Additive per-signal decomposition of ONE scored decision's strategy return.

    share = score·weight / weighted_score, so shares sum to 1 and contributions
    sum to the decision's strategy_return ("+Sentiment 1.8%, +Momentum 2.1% → +4.6%").
    HOLD / zero-conviction rows decompose to all-zero contributions.
    """
    signals = row.get("signals") or {}
    weighted = row.get("weighted_score") or 0.0
    strat = row.get("strategy_return")
    parts = []
    for name, sig in signals.items():
        if not isinstance(sig, dict):
            continue
        score = float(sig.get("score") or 0.0)
        weight = float(sig.get("weight") or 0.0)
        share = (score * weight / weighted) if (score and weighted) else 0.0
        parts.append({
            "signal": name,
            "score": score,
            "weight": round(weight, 4),
            "share": round(share, 4),
            "contribution": round(share * strat, 6) if strat is not None else None,
        })
    parts.sort(key=lambda p: abs(p["contribution"] or 0.0), reverse=True)
    return parts
