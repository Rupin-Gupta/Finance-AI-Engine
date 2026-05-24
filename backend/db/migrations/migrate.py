"""Incremental migration runner. Tracks applied migrations in schema_migrations table."""
import logging
import os
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent
_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_BOOTSTRAP)

        applied: set[str] = {
            row["filename"]
            for row in await conn.fetch("SELECT filename FROM schema_migrations ORDER BY filename")
        }

        sql_files = sorted(
            f for f in _MIGRATIONS_DIR.glob("*.sql")
        )

        for path in sql_files:
            if path.name in applied:
                continue
            sql = path.read_text()
            logger.info("Applying migration: %s", path.name)
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)", path.name
                )
            logger.info("Migration applied: %s", path.name)
