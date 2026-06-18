"""R8: event-proximity confidence gate — pure functions.

A high-impact macro event (Fed/RBI decision, Budget) is a binary shock: even a
technically strong signal can be wiped out by the print. Mirrors the earnings gate
in engine.py but at the market level, so a `.NS` name is gated by RBI/Budget and a
US name by the Fed/CPI. GLOBAL events gate both.
"""
from datetime import date

# Confidence caps by impact + proximity (days until the event).
_EVENT_IMMINENT_DAYS = 1
_EVENT_APPROACHING_DAYS = 3

_HIGH_IMMINENT_CAP = 0.60
_HIGH_APPROACHING_CAP = 0.75
_MEDIUM_IMMINENT_CAP = 0.80

_GATING_IMPACTS = ("high", "medium")


def region_matches(event_region: str, symbol_region: str) -> bool:
    return event_region == "GLOBAL" or event_region == symbol_region


def _as_date(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except (ValueError, TypeError):
        return None


def nearest_gating_event(events: list[dict], today: date, symbol_region: str,
                         max_days: int = 14) -> dict | None:
    """Nearest upcoming high/medium-impact event for the symbol's market.

    events: rows with event_date, event_type, region, impact, title. Low-impact
    events are ignored for gating (still listed by the API). Nearest first; ties
    broken toward higher impact.
    """
    candidates = []
    for e in events:
        if e.get("impact") not in _GATING_IMPACTS:
            continue
        if not region_matches(e.get("region", ""), symbol_region):
            continue
        ed = _as_date(e.get("event_date"))
        if ed is None or ed < today:
            continue
        days = (ed - today).days
        if days > max_days:
            continue
        candidates.append((days, 0 if e["impact"] == "high" else 1, ed, e))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1]))
    days, _, ed, e = candidates[0]
    return {
        "days_to_event": days,
        "impact": e["impact"],
        "event_type": e.get("event_type"),
        "title": e.get("title"),
        "region": e.get("region"),
        "event_date": str(ed),
    }


def event_confidence_cap(days_to_event: int | None, impact: str | None) -> float | None:
    """The confidence ceiling implied by an upcoming event, or None for no cap."""
    if days_to_event is None or impact is None:
        return None
    if impact == "high":
        if days_to_event <= _EVENT_IMMINENT_DAYS:
            return _HIGH_IMMINENT_CAP
        if days_to_event <= _EVENT_APPROACHING_DAYS:
            return _HIGH_APPROACHING_CAP
    elif impact == "medium":
        if days_to_event <= _EVENT_IMMINENT_DAYS:
            return _MEDIUM_IMMINENT_CAP
    return None
