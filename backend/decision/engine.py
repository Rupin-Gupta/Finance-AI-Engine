"""Aggregate signals → BUY/SELL/HOLD + confidence + risk_level."""
from backend.decision.signals import SignalResult

BUY_THRESHOLD = 0.35
SELL_THRESHOLD = -0.35


def _weighted_score(signals: list[SignalResult]) -> float:
    return sum(s.score * s.weight for s in signals)


def _risk_level(vol_20: float | None, weighted: float) -> str:
    if vol_20 is None:
        return "Medium"
    if vol_20 > 0.55 or abs(weighted) > 0.7:
        return "Extreme"
    if vol_20 > 0.40 or abs(weighted) > 0.5:
        return "High"
    if vol_20 > 0.25 or abs(weighted) > 0.3:
        return "Medium"
    return "Low"


def make_recommendation(
    signals: list[SignalResult],
    vol_20: float | None = None,
) -> dict:
    weighted = _weighted_score(signals)
    confidence = round(min(abs(weighted) * 2, 1.0), 4)

    if weighted >= BUY_THRESHOLD:
        recommendation = "BUY"
    elif weighted <= SELL_THRESHOLD:
        recommendation = "SELL"
    else:
        recommendation = "HOLD"

    signals_json = {
        s.name: {
            "score": s.score,
            "weight": s.weight,
            "value": s.value,
            "label": s.label,
        }
        for s in signals
    }

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "weighted_score": round(weighted, 4),
        "risk_level": _risk_level(vol_20, weighted),
        "signals_json": signals_json,
    }
