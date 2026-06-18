import asyncio

from fastapi import APIRouter, Depends, HTTPException

from backend.api.auth import require_api_key
from backend.dependencies import get_db
from backend.db.queries.jobs import get_job, list_jobs

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("")
async def list_jobs_endpoint(limit: int = 30, conn=Depends(get_db)):
    rows = await list_jobs(conn, limit)
    return [dict(r) for r in rows]


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
    from backend.scheduler.jobs.fundamentals_run import run as fundamentals_run
    from backend.scheduler.jobs.corporate_actions_run import run as corporate_actions_run
    from backend.scheduler.jobs.signal_snapshot_run import run as signal_snapshot_run
    from backend.scheduler.jobs.weight_tuning_run import run as weight_tuning_run
    from backend.scheduler.jobs.paper_auto_run import run as paper_auto_run
    from backend.scheduler.jobs.india_signals_run import run as india_signals_run
    from backend.scheduler.jobs.regime_run import run as regime_run
    from backend.scheduler.jobs.events_run import run as events_run
    from backend.scheduler.jobs.stops_run import run as stops_run
    from backend.scheduler.jobs.data_quality_run import run as data_quality_run
    from backend.scheduler.jobs.ml_train_run import run as ml_train_run
    return {
        "market_refresh": market_run,
        "analytics_run": analytics_run,
        "anomaly_scan": anomaly_run,
        "sentiment_run": sentiment_run,
        "decision_run": decision_run,
        "report_run": report_run,
        "fundamentals_run": fundamentals_run,
        "corporate_actions_run": corporate_actions_run,
        "signal_snapshot_run": signal_snapshot_run,
        "weight_tuning_run": weight_tuning_run,
        "paper_auto_run": paper_auto_run,
        "india_signals_run": india_signals_run,
        "regime_run": regime_run,
        "events_run": events_run,
        "stops_run": stops_run,
        "data_quality_run": data_quality_run,
        "ml_train_run": ml_train_run,
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
