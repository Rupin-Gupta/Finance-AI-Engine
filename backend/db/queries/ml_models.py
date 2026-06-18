"""ml_models metadata table access (P14)."""
import asyncpg


async def insert_model(conn: asyncpg.Connection, meta: dict) -> None:
    await conn.execute(
        """
        INSERT INTO ml_models
            (version, horizon, threshold, n_samples, n_features,
             oos_auc, oos_hit_rate, oos_brier, promoted, path, feature_names)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
        meta["version"], meta["horizon"], meta["threshold"], meta.get("n_samples"),
        meta.get("n_features"), meta.get("oos_auc"), meta.get("oos_hit_rate"),
        meta.get("oos_brier"), meta.get("promoted", False), meta["path"],
        meta.get("feature_names"),
    )


async def get_active_model(conn: asyncpg.Connection) -> asyncpg.Record | None:
    """Most recently trained PROMOTED model (the one the engine should use)."""
    return await conn.fetchrow(
        "SELECT * FROM ml_models WHERE promoted = TRUE ORDER BY trained_at DESC LIMIT 1"
    )


async def get_latest_model(conn: asyncpg.Connection) -> asyncpg.Record | None:
    """Most recent model regardless of promotion (for status display)."""
    return await conn.fetchrow("SELECT * FROM ml_models ORDER BY trained_at DESC LIMIT 1")


async def list_models(conn: asyncpg.Connection, limit: int = 10) -> list[asyncpg.Record]:
    return await conn.fetch("SELECT * FROM ml_models ORDER BY trained_at DESC LIMIT $1", limit)
