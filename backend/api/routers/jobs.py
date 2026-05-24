import asyncio

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import require_api_key
from backend.dependencies import get_db
from backend.db.queries.jobs import get_job

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/{job_id}")
async def get_job_status(job_id: str, conn=Depends(get_db)):
    row = await get_job(conn, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


def _get_job_runners() -> dict:
    from backend.scheduler.jobs.market_refresh import run as market_run
    from backend.scheduler.jobs.analytics_run import run as analytics_run
    from backend.scheduler.jobs.anomaly_scan import run as anomaly_run
    from backend.scheduler.jobs.sentiment_run import run as sentiment_run
    from backend.scheduler.jobs.decision_run import run as decision_run
    from backend.scheduler.jobs.report_run import run as report_run
    return {
        "market_refresh": market_run,
        "analytics_run": analytics_run,
        "anomaly_scan": anomaly_run,
        "sentiment_run": sentiment_run,
        "decision_run": decision_run,
        "report_run": report_run,
    }


@router.post("/trigger/{job_name}", status_code=202)
async def trigger_job(job_name: str):
    """Fire a scheduler job immediately in the background. Returns 202 Accepted."""
    runners = _get_job_runners()
    if job_name not in runners:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown job '{job_name}'. Valid jobs: {sorted(runners)}",
        )
    asyncio.create_task(runners[job_name]())
    return {"status": "accepted", "job": job_name}
