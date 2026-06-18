"""P3: stop-loss / trailing-stop tracking — pure functions.

Completes "BUY → how much (R2), where's my downside (R6 VaR), and where do I get out".
A trailing stop ratchets up with the high-water mark since entry and never down, so it
locks in gains; a fixed stop sits at a constant % below entry. Stop width is volatility-
derived (ATR-style: wider for noisier names so normal swings don't whipsaw you out),
clamped, and trimmed by the decision's risk level — all overridable per symbol.
"""
import math

DEFAULT_STOP_PCT = 0.08
_MIN_STOP_PCT = 0.03
_MAX_STOP_PCT = 0.25
_VOL_MULT = 3.0            # ~3 daily σ → stop distance
_TRADING_DAYS = 252

# Wider stops for higher-risk names (more noise to ride through), capped by _MAX.
_RISK_MULT = {"Low": 0.8, "Medium": 1.0, "High": 1.25, "Extreme": 1.5}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def recommended_stop_pct(vol_20: float | None, risk_level: str | None) -> float:
    """Vol-derived stop distance (fraction), risk-level-trimmed and clamped."""
    if vol_20 is not None and vol_20 > 0:
        daily = vol_20 / math.sqrt(_TRADING_DAYS)
        base = daily * _VOL_MULT
    else:
        base = DEFAULT_STOP_PCT
    base *= _RISK_MULT.get(risk_level, 1.0)
    return round(_clamp(base, _MIN_STOP_PCT, _MAX_STOP_PCT), 4)


def stop_level(entry: float, high_water: float | None, stop_pct: float, trailing: bool) -> float:
    """Trailing → from the high-water mark since entry (never below entry's own stop)."""
    ref = entry
    if trailing and high_water is not None:
        ref = max(entry, high_water)
    return round(ref * (1.0 - stop_pct), 4)


def evaluate_stop(entry: float | None, current: float | None, high_water: float | None,
                  stop_pct: float, trailing: bool) -> dict | None:
    """Stop level + breach flag + distances for one position. None if no entry/current."""
    if entry is None or entry <= 0 or current is None:
        return None
    level = stop_level(entry, high_water, stop_pct, trailing)
    breached = current <= level
    return {
        "stop_pct": round(stop_pct, 4),
        "trailing": trailing,
        "stop_level": level,
        "current": round(current, 4),
        "breached": breached,
        # how far current sits above the stop (negative once breached)
        "distance_pct": round((current - level) / current, 4) if current else None,
        # P&L locked in if stopped out from entry (trailing can make this positive)
        "stop_pl_pct": round((level - entry) / entry, 4),
    }


def position_stop(entry: float | None, current: float | None, high_water: float | None,
                  vol_20: float | None = None, risk_level: str | None = None,
                  stop_pct: float | None = None, trailing: bool = True) -> dict | None:
    """Full stop assessment; uses the recommended pct unless an override is given."""
    pct = stop_pct if stop_pct is not None else recommended_stop_pct(vol_20, risk_level)
    ev = evaluate_stop(entry, current, high_water, pct, trailing)
    if ev is None:
        return None
    ev["recommended"] = stop_pct is None
    return ev
