from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.dependencies import get_db
from backend.db.queries.alerts import list_alerts

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("")
async def get_alerts(symbol: str | None = None, limit: int = 50, conn=Depends(get_db)):
    rows = await list_alerts(conn, symbol=symbol, limit=limit)
    return [dict(r) for r in rows]
