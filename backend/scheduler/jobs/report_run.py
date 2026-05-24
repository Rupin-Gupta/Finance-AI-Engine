from backend.db.connection import get_db_pool
from backend.db.queries.jobs import create_job, update_job_status
from backend.reporting.sector_report import run_sector_report


async def run() -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        job_id = await create_job(conn, "report_run")
        try:
            await run_sector_report(conn)
            await update_job_status(conn, job_id, "completed")
        except Exception as exc:
            await update_job_status(conn, job_id, "failed", error=str(exc))
            raise
