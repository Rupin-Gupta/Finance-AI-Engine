import json

import asyncpg


async def insert_weight_set(conn: asyncpg.Connection, result: dict, promoted: bool) -> None:
    """Persist one tuning run (from weight_tuning.walk_forward / walk_forward_expanding).

    Columns hold whichever objective the run optimized (return / net-of-cost / Sharpe);
    prefers the normalized scalars, falling back to the nested avg_return for old callers.
    """
    oos = result.get("out_of_sample") or {}
    base_oos = result.get("base_out_of_sample") or {}
    in_s = result.get("in_sample") or {}
    await conn.execute(
        """
        INSERT INTO signal_weights
            (weights_json, in_sample_return, out_of_sample_return,
             base_out_of_sample_return, improvement, promoted)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        json.dumps(result["weights"]),
        result.get("in_sample_metric", in_s.get("avg_return")),
        result.get("oos_metric", oos.get("avg_return")),
        result.get("base_oos_metric", base_oos.get("avg_return")),
        result.get("improvement"),
        promoted,
    )


async def get_active_weights(conn: asyncpg.Connection) -> dict | None:
    """Latest promoted weight set, or None (→ engine falls back to SIGNAL_WEIGHTS)."""
    row = await conn.fetchrow(
        "SELECT weights_json FROM signal_weights WHERE promoted ORDER BY created_at DESC LIMIT 1"
    )
    if not row:
        return None
    raw = row["weights_json"]
    return json.loads(raw) if isinstance(raw, str) else raw


async def list_weight_sets(conn: asyncpg.Connection, limit: int = 20) -> list[asyncpg.Record]:
    return await conn.fetch(
        """
        SELECT weights_json, in_sample_return, out_of_sample_return,
               base_out_of_sample_return, improvement, promoted, created_at
        FROM signal_weights ORDER BY created_at DESC LIMIT $1
        """,
        limit,
    )
