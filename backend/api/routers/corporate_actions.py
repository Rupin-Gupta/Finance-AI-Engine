"""Corporate actions viewer — splits / bonus / dividends / rights per symbol."""
import asyncpg
from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.api.validators import validated_symbol
from backend.dependencies import get_db
from backend.db.queries.corporate_actions import get_corporate_actions

router = APIRouter(dependencies=[Depends(require_api_key)])


def _f(v) -> float | None:
    return float(v) if v is not None else None


@router.get("/{symbol}")
async def list_corporate_actions(sym: str = Depends(validated_symbol), conn: asyncpg.Connection = Depends(get_db)) -> dict:
    rows = await get_corporate_actions(conn, sym)
    return {
        "symbol": sym,
        "actions": [
            {
                "date": str(r["action_date"]),
                "type": r["action_type"],
                "ratio": _f(r["ratio"]),
                "amount": _f(r["amount"]),
            }
            for r in rows
        ],
    }
