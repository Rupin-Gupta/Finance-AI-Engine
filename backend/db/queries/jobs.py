import asyncpg
from datetime import datetime


async def create_job(conn: asyncpg.Connection, job_type: str) -> str:
    row = await conn.fetchrow(
        "INSERT INTO jobs (type, status, started_at) VALUES ($1, 'running', now()) RETURNING id",
        job_type,
    )
    return str(row["id"])


async def update_job_status(conn: asyncpg.Connection, job_id: str,
                             status: str, error: str | None = None) -> None:
    await conn.execute(
        "UPDATE jobs SET status=$1, finished_at=now(), error=$2 WHERE id=$3",
        status, error, job_id,
    )


async def get_job(conn: asyncpg.Connection, job_id: str) -> asyncpg.Record | None:
    return await conn.fetchrow("SELECT * FROM jobs WHERE id=$1", job_id)


async def list_jobs(conn: asyncpg.Connection, limit: int = 30) -> list[asyncpg.Record]:
    return await conn.fetch(
        "SELECT id, type, status, started_at, finished_at, error FROM jobs ORDER BY started_at DESC LIMIT $1",
        limit,
    )
