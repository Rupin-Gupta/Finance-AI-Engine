"""Recommendation accuracy: did past BUY/SELL/HOLD calls pay off vs realized prices?

Pure functions — no I/O — so the scoring logic is fully unit-testable.
The router resolves entry/exit prices from market_data and feeds them here.
"""
from datetime import date

# A HOLD is judged "correct" when price stayed within ±this band over the horizon.
HOLD_BAND = 0.02


def resolve_price(
    series: list[tuple[date, float]], target: date, mode: str
) -> float | None:
    """Pick a close from a date-sorted [(date, close)] series.

    mode="on_or_before": latest close on/before target (entry — nearest prior trading day).
    mode="on_or_after":  earliest close on/after target (exit — nearest following trading day).
    """
    if not series:
        return None
    if mode == "on_or_before":
        chosen = None
        for d, c in series:
            if d <= target:
                chosen = c
            else:
                break
        return chosen
    if mode == "on_or_after":
        for d, c in series:
            if d >= target:
                return c
        return None
    raise ValueError(f"unknown mode: {mode}")


def evaluate_decision(recommendation: str, entry: float | None, exit_: float | None) -> dict | None:
    """Score one decision. Returns None when prices are missing (not yet evaluable)."""
    if entry is None or exit_ is None or entry == 0:
        return None
    move = (exit_ - entry) / entry
    if recommendation == "BUY":
        strategy_return = move
        correct = move > 0
    elif recommendation == "SELL":
        strategy_return = -move
        correct = move < 0
    else:  # HOLD — flat call, no position taken
        strategy_return = 0.0
        correct = abs(move) <= HOLD_BAND
    return {
        "realized_move": round(move, 6),
        "strategy_return": round(strategy_return, 6),
        "correct": correct,
    }


def _group_stats(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"count": 0, "hit_rate": None, "avg_return": None}
    hits = sum(1 for r in rows if r["correct"])
    avg = sum(r["strategy_return"] for r in rows) / n
    return {"count": n, "hit_rate": round(hits / n, 4), "avg_return": round(avg, 6)}


def aggregate_performance(evaluated: list[dict]) -> dict:
    """Aggregate scored decisions into overall + by-recommendation + by-risk-level stats.

    Each row must carry: recommendation, risk_level, strategy_return, correct.
    """
    overall = _group_stats(evaluated)

    by_recommendation = {}
    for rec in ("BUY", "SELL", "HOLD"):
        subset = [r for r in evaluated if r["recommendation"] == rec]
        if subset:
            by_recommendation[rec] = _group_stats(subset)

    by_risk = {}
    risk_levels = sorted({r["risk_level"] for r in evaluated if r.get("risk_level")})
    for rl in risk_levels:
        by_risk[rl] = _group_stats([r for r in evaluated if r.get("risk_level") == rl])

    # Cumulative compounded return of the strategy (treating each call as a sequential bet).
    cumulative = 1.0
    for r in evaluated:
        cumulative *= 1 + r["strategy_return"]

    return {
        "overall": overall,
        "by_recommendation": by_recommendation,
        "by_risk_level": by_risk,
        "cumulative_return": round(cumulative - 1.0, 6),
    }
