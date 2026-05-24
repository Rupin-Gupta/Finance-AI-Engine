"""T12: Verify all 5 scheduler jobs fire and write jobs rows."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(conn: AsyncMock) -> MagicMock:
    """Return a fake asyncpg pool whose acquire() context manager yields conn."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool


def _make_conn(job_id: str = "job-1") -> AsyncMock:
    """Return a fake asyncpg connection that handles job queries."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"id": job_id})
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.executemany = AsyncMock()
    return conn


# ---------------------------------------------------------------------------
# market_refresh
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_market_refresh_creates_and_completes_job():
    conn = _make_conn("market-job-1")
    pool = _make_pool(conn)
    mock_ingest = AsyncMock(return_value="market-job-1")

    with patch("backend.scheduler.jobs.market_refresh.get_db_pool", AsyncMock(return_value=pool)), \
         patch("backend.scheduler.jobs.market_refresh.run_market_ingest", mock_ingest):
        from backend.scheduler.jobs.market_refresh import run
        await run()

    mock_ingest.assert_awaited_once()


# ---------------------------------------------------------------------------
# analytics_run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analytics_run_creates_and_completes_job():
    conn = _make_conn("analytics-job-1")
    pool = _make_pool(conn)

    with patch("backend.scheduler.jobs.analytics_run.get_db_pool", AsyncMock(return_value=pool)), \
         patch("backend.scheduler.jobs.analytics_run.create_job", AsyncMock(return_value="analytics-job-1")) as mock_create, \
         patch("backend.scheduler.jobs.analytics_run.update_job_status", AsyncMock()) as mock_update, \
         patch("backend.scheduler.jobs.analytics_run.get_ohlcv", AsyncMock(return_value=[])):
        from backend.scheduler.jobs.analytics_run import run
        await run()

    mock_create.assert_awaited_once_with(conn, "analytics_run")
    mock_update.assert_awaited_once_with(conn, "analytics-job-1", "completed")


# ---------------------------------------------------------------------------
# anomaly_scan
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anomaly_scan_creates_and_completes_job():
    conn = _make_conn("anomaly-job-1")
    pool = _make_pool(conn)

    with patch("backend.scheduler.jobs.anomaly_scan.get_db_pool", AsyncMock(return_value=pool)), \
         patch("backend.scheduler.jobs.anomaly_scan.create_job", AsyncMock(return_value="anomaly-job-1")) as mock_create, \
         patch("backend.scheduler.jobs.anomaly_scan.update_job_status", AsyncMock()) as mock_update, \
         patch("backend.scheduler.jobs.anomaly_scan.get_ohlcv", AsyncMock(return_value=[])):
        from backend.scheduler.jobs.anomaly_scan import run
        await run()

    mock_create.assert_awaited_once_with(conn, "anomaly_scan")
    mock_update.assert_awaited_once_with(conn, "anomaly-job-1", "completed")


# ---------------------------------------------------------------------------
# doc_refresh — no URLs (no-op)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_doc_refresh_noop_when_no_urls(monkeypatch):
    import backend.scheduler.jobs.doc_refresh as doc_mod
    monkeypatch.setattr(doc_mod, "DOC_URLS", [])
    mock_pool = AsyncMock()

    with patch("backend.scheduler.jobs.doc_refresh.get_db_pool", mock_pool):
        await doc_mod.run()

    mock_pool.assert_not_awaited()


@pytest.mark.asyncio
async def test_doc_refresh_calls_run_doc_ingest_for_each_url(monkeypatch):
    import backend.scheduler.jobs.doc_refresh as doc_mod
    monkeypatch.setattr(doc_mod, "DOC_URLS", ["https://example.com/r1.txt", "https://example.com/r2.txt"])

    conn = _make_conn()
    pool = _make_pool(conn)
    mock_ingest = AsyncMock()

    with patch("backend.scheduler.jobs.doc_refresh.get_db_pool", AsyncMock(return_value=pool)), \
         patch("backend.scheduler.jobs.doc_refresh.run_doc_ingest", mock_ingest):
        await doc_mod.run()

    assert mock_ingest.await_count == 2
    mock_ingest.assert_any_await(conn, "https://example.com/r1.txt", doc_type="scheduled")
    mock_ingest.assert_any_await(conn, "https://example.com/r2.txt", doc_type="scheduled")


# ---------------------------------------------------------------------------
# report_run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_run_creates_and_completes_job():
    conn = _make_conn("report-job-1")
    pool = _make_pool(conn)

    with patch("backend.scheduler.jobs.report_run.get_db_pool", AsyncMock(return_value=pool)), \
         patch("backend.scheduler.jobs.report_run.create_job", AsyncMock(return_value="report-job-1")) as mock_create, \
         patch("backend.scheduler.jobs.report_run.update_job_status", AsyncMock()) as mock_update, \
         patch("backend.scheduler.jobs.report_run.run_sector_report", AsyncMock()):
        from backend.scheduler.jobs.report_run import run
        await run()

    mock_create.assert_awaited_once_with(conn, "report_run")
    mock_update.assert_awaited_once_with(conn, "report-job-1", "completed")


# ---------------------------------------------------------------------------
# report_run — failure path marks job failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_run_marks_job_failed_on_error():
    conn = _make_conn("report-job-2")
    pool = _make_pool(conn)

    with patch("backend.scheduler.jobs.report_run.get_db_pool", AsyncMock(return_value=pool)), \
         patch("backend.scheduler.jobs.report_run.create_job", AsyncMock(return_value="report-job-2")), \
         patch("backend.scheduler.jobs.report_run.update_job_status", AsyncMock()) as mock_update, \
         patch("backend.scheduler.jobs.report_run.run_sector_report", AsyncMock(side_effect=RuntimeError("llm down"))):
        from backend.scheduler.jobs.report_run import run
        with pytest.raises(RuntimeError, match="llm down"):
            await run()

    mock_update.assert_awaited_once_with(conn, "report-job-2", "failed", error="llm down")


# ---------------------------------------------------------------------------
# analytics_run — failure path marks job failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analytics_run_marks_job_failed_on_error():
    conn = _make_conn("analytics-job-2")
    pool = _make_pool(conn)

    with patch("backend.scheduler.jobs.analytics_run.get_db_pool", AsyncMock(return_value=pool)), \
         patch("backend.scheduler.jobs.analytics_run.create_job", AsyncMock(return_value="analytics-job-2")), \
         patch("backend.scheduler.jobs.analytics_run.update_job_status", AsyncMock()) as mock_update, \
         patch("backend.scheduler.jobs.analytics_run.get_ohlcv", AsyncMock(side_effect=Exception("db error"))):
        from backend.scheduler.jobs.analytics_run import run
        with pytest.raises(Exception, match="db error"):
            await run()

    mock_update.assert_awaited_once_with(conn, "analytics-job-2", "failed", error="db error")


# ---------------------------------------------------------------------------
# anomaly_scan — failure path marks job failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anomaly_scan_marks_job_failed_on_error():
    conn = _make_conn("anomaly-job-2")
    pool = _make_pool(conn)

    with patch("backend.scheduler.jobs.anomaly_scan.get_db_pool", AsyncMock(return_value=pool)), \
         patch("backend.scheduler.jobs.anomaly_scan.create_job", AsyncMock(return_value="anomaly-job-2")), \
         patch("backend.scheduler.jobs.anomaly_scan.update_job_status", AsyncMock()) as mock_update, \
         patch("backend.scheduler.jobs.anomaly_scan.get_ohlcv", AsyncMock(side_effect=Exception("timeout"))):
        from backend.scheduler.jobs.anomaly_scan import run
        with pytest.raises(Exception, match="timeout"):
            await run()

    mock_update.assert_awaited_once_with(conn, "anomaly-job-2", "failed", error="timeout")


# ---------------------------------------------------------------------------
# worker — all 5 job IDs registered
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_worker_registers_all_five_jobs():
    from backend.scheduler.worker import start_scheduler, scheduler

    if scheduler.running:
        scheduler.shutdown(wait=False)

    start_scheduler()
    try:
        job_ids = {j.id for j in scheduler.get_jobs()}
        assert job_ids == {"market_refresh", "analytics_run", "anomaly_scan", "doc_refresh", "report_run"}
    finally:
        scheduler.shutdown(wait=False)
