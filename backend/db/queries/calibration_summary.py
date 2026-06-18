"""Read-cache for the calibration snapshot (R2.1).

Written by signal_snapshot_run, read by the decision endpoint to derive a calibrated
win probability cheaply (one row) instead of re-scoring history on every request.
"""
import json

import asyncpg


async def upsert_calibration_summary(
    conn: asyncpg.Connection, horizon_days: int, summary: dict
) -> None:
    await conn.execute(
        """
        INSERT INTO calibration_summary
            (horizon_days, reliability_json, by_recommendation_json,
             overall_hit_rate, evaluated_count)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (horizon_days) DO UPDATE SET
            reliability_json       = EXCLUDED.reliability_json,
            by_recommendation_json = EXCLUDED.by_recommendation_json,
            overall_hit_rate       = EXCLUDED.overall_hit_rate,
            evaluated_count        = EXCLUDED.evaluated_count,
            updated_at             = now()
        """,
        horizon_days,
        json.dumps(summary.get("reliability") or {}),
        json.dumps(summary.get("by_recommendation") or {}),
        summary.get("overall_hit_rate"),
        summary.get("count", 0),
    )


def _loads(raw):
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


async def get_calibration_summary(
    conn: asyncpg.Connection, horizon_days: int = 5
) -> dict | None:
    """Latest persisted calibration snapshot for a horizon, or None if never run."""
    row = await conn.fetchrow(
        "SELECT * FROM calibration_summary WHERE horizon_days = $1", horizon_days
    )
    if not row:
        return None
    return {
        "reliability": _loads(row["reliability_json"]),
        "by_recommendation": _loads(row["by_recommendation_json"]),
        "overall_hit_rate": float(row["overall_hit_rate"]) if row["overall_hit_rate"] is not None else None,
        "count": row["evaluated_count"],
        "updated_at": str(row["updated_at"]),
    }
