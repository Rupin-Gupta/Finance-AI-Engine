"""ML directional model status (P14): active/latest model + out-of-sample metrics."""
import asyncpg
from fastapi import APIRouter, Depends, Request

from backend.api.auth import require_api_key
from backend.api.limiter import limiter
from backend.dependencies import get_db
from backend.db.queries.ml_models import get_active_model, get_latest_model, list_models
from backend.decision.signals import ML_SIGNAL_WEIGHT

router = APIRouter(dependencies=[Depends(require_api_key)])


def _f(v):
    return float(v) if v is not None else None


def _row(r) -> dict | None:
    if not r:
        return None
    return {
        "version": r["version"], "trained_at": str(r["trained_at"]),
        "horizon": r["horizon"], "threshold": _f(r["threshold"]),
        "n_samples": r["n_samples"], "oos_auc": _f(r["oos_auc"]),
        "oos_hit_rate": _f(r["oos_hit_rate"]), "oos_brier": _f(r["oos_brier"]),
        "promoted": r["promoted"], "feature_names": list(r["feature_names"] or []),
    }


@router.get("/model")
@limiter.limit("30/minute")
async def ml_model(request: Request, conn: asyncpg.Connection = Depends(get_db)) -> dict:
    """Active (promoted) model the engine uses + the latest trained model + recent history."""
    active = await get_active_model(conn)
    latest = await get_latest_model(conn)
    history = await list_models(conn, limit=10)
    return {
        "active": _row(active),
        "latest": _row(latest),
        "signal_weight": ML_SIGNAL_WEIGHT,
        "in_use": active is not None,
        "history": [_row(h) for h in history],
    }
