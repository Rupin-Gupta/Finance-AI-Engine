"""Aggregate signals → BUY/SELL/HOLD + confidence + risk_level."""
from backend.decision.signals import SignalResult

# Lowered from ±0.35: graduated 5-level scoring distributes mass more evenly.
BUY_THRESHOLD  =  0.30
SELL_THRESHOLD = -0.30

# 8 signals now — consensus threshold raised from 5 to 6.
_CONSENSUS_THRESHOLD = 6
_CONSENSUS_BOOST      = 1.15
_EXTREME_VOL_THRESHOLD = 0.55
_EXTREME_VOL_CONF_CAP  = 0.70

# Earnings proximity confidence caps.
_EARNINGS_IMMINENT_DAYS      = 7
_EARNINGS_APPROACHING_DAYS   = 14
_EARNINGS_IMMINENT_CONF_CAP  = 0.65
_EARNINGS_APPROACHING_CONF_CAP = 0.80


def _weighted_score(signals: list[SignalResult]) -> float:
    return sum(s.score * s.weight for s in signals)


def _consensus_confidence(signals: list[SignalResult], confidence: float) -> float:
    """Boost confidence when ≥6/8 signals agree on direction; cap at 0.99."""
    bull = sum(1 for s in signals if s.score > 0)
    bear = sum(1 for s in signals if s.score < 0)
    if max(bull, bear) >= _CONSENSUS_THRESHOLD:
        confidence = min(confidence * _CONSENSUS_BOOST, 0.99)
    return confidence


def _apply_vol_cap(vol_20: float | None, confidence: float) -> float:
    """In extreme volatility, cap confidence — signal reliability drops."""
    if vol_20 is not None and vol_20 > _EXTREME_VOL_THRESHOLD:
        confidence = min(confidence, _EXTREME_VOL_CONF_CAP)
    return confidence


def _apply_earnings_gate(days_to_earnings: int | None, confidence: float) -> float:
    """Cap confidence near earnings — binary event risk makes signals unreliable."""
    if days_to_earnings is None:
        return confidence
    if days_to_earnings <= _EARNINGS_IMMINENT_DAYS:
        return min(confidence, _EARNINGS_IMMINENT_CONF_CAP)
    if days_to_earnings <= _EARNINGS_APPROACHING_DAYS:
        return min(confidence, _EARNINGS_APPROACHING_CONF_CAP)
    return confidence


def _apply_regime_cap(regime: str | None, confidence: float) -> float:
    """R5: in a market-wide high-vol regime, cap confidence like the per-symbol vol cap."""
    if regime == "high_vol":
        from backend.analytics.regime import HIGH_VOL_CONF_CAP
        return min(confidence, HIGH_VOL_CONF_CAP)
    return confidence


def _apply_event_gate(event_context: dict | None, confidence: float) -> float:
    """R8: cap confidence ahead of a high-impact macro event (Fed/RBI/Budget)."""
    if not event_context:
        return confidence
    from backend.analytics.events import event_confidence_cap
    cap = event_confidence_cap(event_context.get("days_to_event"), event_context.get("impact"))
    return min(confidence, cap) if cap is not None else confidence


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
    days_to_earnings: int | None = None,
    regime: str | None = None,
    event_context: dict | None = None,
) -> dict:
    weighted = _weighted_score(signals)

    # Base confidence: scale weighted score to [0, 1]
    confidence = round(min(abs(weighted) * 2, 1.0), 4)

    # Adjust for consensus, extreme vol, earnings proximity, market regime, macro events
    confidence = _consensus_confidence(signals, confidence)
    confidence = _apply_vol_cap(vol_20, confidence)
    confidence = _apply_earnings_gate(days_to_earnings, confidence)
    confidence = _apply_regime_cap(regime, confidence)
    confidence = _apply_event_gate(event_context, confidence)
    confidence = round(confidence, 4)

    if weighted >= BUY_THRESHOLD:
        recommendation = "BUY"
    elif weighted <= SELL_THRESHOLD:
        recommendation = "SELL"
    else:
        recommendation = "HOLD"

    signals_json = {
        s.name: {
            "score":  s.score,
            "weight": s.weight,
            "value":  s.value,
            "label":  s.label,
        }
        for s in signals
    }

    return {
        "recommendation": recommendation,
        "confidence":     confidence,
        "weighted_score": round(weighted, 4),
        "risk_level":     _risk_level(vol_20, weighted),
        "signals_json":   signals_json,
        "days_to_earnings": days_to_earnings,
        "regime": regime,
        "event_context": event_context,
    }
