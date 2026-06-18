"""Position sizing — pure, no I/O. Answers "how much should I buy?" as a % of portfolio.

Three independent models, then the most conservative (min) is recommended:
  - Kelly (fractional): edge from win probability, symmetric-payoff f* = 2p - 1, scaled by
    a safety fraction (half-Kelly). Uses the calibrated hit rate if known, else confidence.
  - Volatility target: scale inversely with annualized volatility (target_vol / vol).
  - Risk budget: risk a fixed % of the book per trade given a stop distance derived from vol.

Then a risk-level multiplier trims High/Extreme-risk names, and everything is capped.
"""
import math

_RISK_MULT = {"Low": 1.0, "Medium": 0.75, "High": 0.5, "Extreme": 0.25}


def _flt(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def recommend_size(
    confidence,
    vol_annualized,
    risk_level: str | None,
    win_prob=None,
    max_position: float = 0.20,
    target_vol: float = 0.15,
    risk_per_trade: float = 0.01,
    min_stop: float = 0.05,
    kelly_fraction: float = 0.5,
) -> dict:
    """Return sizing breakdown + a recommended position fraction (0..max_position)."""
    confidence = _flt(confidence)
    vol = _flt(vol_annualized)
    p = _flt(win_prob)
    if p is None:
        p = confidence if confidence is not None else 0.5

    # --- Kelly (half) on a symmetric payoff ---
    kelly_full = max(0.0, 2.0 * p - 1.0)
    kelly = kelly_full * kelly_fraction

    # --- Volatility target ---
    if vol and vol > 0:
        vol_target = target_vol / vol
    else:
        vol_target = max_position

    # --- Risk budget with a vol-derived stop (2σ daily, floored) ---
    if vol and vol > 0:
        stop = max(min_stop, 2.0 * vol / math.sqrt(252))
    else:
        stop = min_stop
    risk_budget = risk_per_trade / stop

    risk_mult = _RISK_MULT.get(risk_level, 0.75)

    # Most conservative of the three, trimmed by risk level, then capped.
    raw = min(kelly, vol_target, risk_budget)
    recommended = max(0.0, min(raw * risk_mult, max_position))

    # Reason: which constraint bound the size (or no-edge).
    if kelly_full <= 0:
        reason = "No positive edge (win prob ≤ 50%) — recommend staying flat."
    else:
        binding = min((kelly, "Kelly"), (vol_target, "volatility"), (risk_budget, "risk budget"),
                      key=lambda x: x[0])[1]
        reason = (f"Bound by {binding}; trimmed ×{risk_mult:g} for {risk_level or 'Medium'} risk "
                  f"(cap {max_position:.0%}).")

    return {
        "recommended_pct": round(recommended, 4),
        "kelly_pct": round(min(kelly, max_position), 4),
        "vol_target_pct": round(min(vol_target, max_position), 4),
        "risk_budget_pct": round(min(risk_budget, max_position), 4),
        "win_prob": round(p, 4),
        "risk_multiplier": risk_mult,
        "stop_distance": round(stop, 4),
        "reason": reason,
    }
