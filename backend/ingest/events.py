"""R8: macro event calendar source.

Scheduled macro events (central-bank decisions, CPI prints, the Union Budget) are
published well in advance, so a curated calendar is the honest free source — no
anti-bot scraping like NSE (P5). `fetch_market_events` is PURE (takes `today`, no
network) and fully testable; a real economic-calendar API can later replace the
curated tables without touching the gate, the job, or the schema.

Region semantics: US / INDIA events gate only their own market; GLOBAL gates both.
"""
from datetime import date, timedelta

SOURCE = "curated"

# --- US FOMC rate-decision announcement days (2-day meeting → the 2nd day) ---
_FOMC = [
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17),
    date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
    date(2027, 1, 27), date(2027, 3, 17),
]

# --- RBI Monetary Policy Committee resolution days (bi-monthly, approx) ---
_RBI_MPC = [
    date(2026, 2, 6), date(2026, 4, 8), date(2026, 6, 5), date(2026, 8, 5),
    date(2026, 10, 1), date(2026, 12, 4), date(2027, 2, 5),
]

# --- India Union Budget ---
_BUDGET = [date(2026, 2, 1), date(2027, 2, 1)]


def _cpi_events(today: date, horizon_days: int) -> list[dict]:
    """US CPI prints land ~mid-month; generate the upcoming ones in the window."""
    out = []
    end = today + timedelta(days=horizon_days)
    y, m = today.year, today.month
    for _ in range(14):  # enough months to cover any reasonable horizon
        try:
            d = date(y, m, 12)
        except ValueError:
            d = date(y, m, 28)
        if d >= today and d <= end:
            out.append({"event_date": d, "event_type": "CPI", "region": "US",
                        "impact": "medium", "title": f"US CPI release ({d:%b %Y})"})
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def fetch_market_events(today: date | None = None, horizon_days: int = 120) -> list[dict]:
    """Return upcoming scheduled macro events within the horizon (deduped, sorted)."""
    today = today or date.today()
    end = today + timedelta(days=horizon_days)
    events: list[dict] = []

    for d in _FOMC:
        if today <= d <= end:
            events.append({"event_date": d, "event_type": "FOMC", "region": "US",
                           "impact": "high", "title": "US Fed FOMC rate decision"})
    for d in _RBI_MPC:
        if today <= d <= end:
            events.append({"event_date": d, "event_type": "RBI_MPC", "region": "INDIA",
                           "impact": "high", "title": "RBI Monetary Policy decision"})
    for d in _BUDGET:
        if today <= d <= end:
            events.append({"event_date": d, "event_type": "BUDGET", "region": "INDIA",
                           "impact": "high", "title": "India Union Budget"})
    events.extend(_cpi_events(today, horizon_days))

    for e in events:
        e["source"] = SOURCE
    events.sort(key=lambda e: e["event_date"])
    return events
