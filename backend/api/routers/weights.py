"""Signal weights — current (auto-tuned or default) + tuning-run history (R4)."""
import json

import asyncpg
from fastapi import APIRouter, Depends

from backend.api.auth import require_api_key
from backend.dependencies import get_db
from backend.db.queries.signal_weights import get_active_weights, list_weight_sets
from backend.decision.signals import SIGNAL_WEIGHTS

router = APIRouter(dependencies=[Depends(require_api_key)])


def _f(v):
    return float(v) if v is not None else None


@router.get("")
async def get_weights(conn: asyncpg.Connection = Depends(get_db)) -> dict:
    active = await get_active_weights(conn)
    rows = await list_weight_sets(conn)
    return {
        "default_weights": SIGNAL_WEIGHTS,
        "active_weights": active or SIGNAL_WEIGHTS,
        "using_tuned": active is not None,
        "history": [
            {
                "weights": json.loads(r["weights_json"]) if isinstance(r["weights_json"], str) else r["weights_json"],
                "in_sample_return": _f(r["in_sample_return"]),
                "out_of_sample_return": _f(r["out_of_sample_return"]),
                "base_out_of_sample_return": _f(r["base_out_of_sample_return"]),
                "improvement": _f(r["improvement"]),
                "promoted": r["promoted"],
                "created_at": str(r["created_at"]),
            }
            for r in rows
        ],
    }
