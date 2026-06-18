"""Macro event calendar (R8): upcoming Fed/RBI/CPI/Budget events + the gate they drive."""
import asyncpg
from fastapi import APIRouter, Depends, Query, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.dependencies import get_db
from backend.db.queries.events import get_upcoming_events

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("")
@limiter.limit("30/minute")
async def list_events(
    request: Request,
    region: str | None = Query(default=None, description="US | INDIA (also returns GLOBAL); omit for all"),
    days: int = Query(default=90, ge=1, le=365),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    reg = region.strip().upper() if region else None
    rows = await get_upcoming_events(conn, days=days, region=reg if reg in ("US", "INDIA") else None)
    return {
        "region": reg,
        "days": days,
        "events": [
            {"date": str(r["event_date"]), "type": r["event_type"], "region": r["region"],
             "impact": r["impact"], "title": r["title"], "source": r["source"]}
            for r in rows
        ],
    }
