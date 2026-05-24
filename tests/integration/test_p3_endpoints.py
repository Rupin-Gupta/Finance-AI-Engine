"""Integration tests added in P3 hardening pass."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import io

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.dependencies import get_db
from backend.config import settings

API_KEY = settings.api_key
AUTH = {"X-API-Key": API_KEY}


class FakeConn:
    def __init__(self, job_id="job-1"):
        self._job_id = job_id
        self.job_updates: list = []

    async def fetchrow(self, query, *args):
        if "INSERT INTO jobs" in query:
            return {"id": self._job_id}
        return None

    async def execute(self, query, *args):
        if "UPDATE jobs" in query:
            self.job_updates.append(args)

    async def executemany(self, query, rows):
        pass

    async def fetch(self, query, *args):
        return []


def _override(conn):
    async def _dep():
        yield conn
    return _dep


# ---------------------------------------------------------------------------
# Upload: 413 on file > 10 MB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_413_on_oversized_file():
    big = b"x" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ingest/upload",
            headers=AUTH,
            files={"file": ("big.txt", io.BytesIO(big), "text/plain")},
            data={"doc_type": "report"},
        )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_upload_accepts_small_file():
    conn = FakeConn("job-upload-ok")
    app.dependency_overrides[get_db] = _override(conn)
    try:
        with patch("backend.api.routers.ingest.run_text_ingest", AsyncMock(return_value="job-upload-ok")):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/ingest/upload",
                    headers=AUTH,
                    files={"file": ("report.txt", io.BytesIO(b"Some financial text."), "text/plain")},
                    data={"doc_type": "report"},
                )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["job_id"] == "job-upload-ok"


# ---------------------------------------------------------------------------
# SSRF: /v1/ingest/docs rejects private IPs and localhost
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("bad_url", [
    "http://localhost/secret",
    "http://127.0.0.1/admin",
    "http://192.168.1.1/internal",
    "http://10.0.0.1/metadata",
    "http://169.254.169.254/latest/meta-data/",
    "ftp://example.com/file.txt",
    "file:///etc/passwd",
])
async def test_ingest_docs_rejects_ssrf_urls(bad_url):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ingest/docs",
            headers=AUTH,
            json={"source_url": bad_url, "doc_type": "report"},
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_docs_accepts_public_url():
    conn = FakeConn("job-docs-ok")
    app.dependency_overrides[get_db] = _override(conn)
    try:
        with patch("backend.api.routers.ingest.run_doc_ingest", AsyncMock(return_value="job-docs-ok")):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/ingest/docs",
                    headers=AUTH,
                    json={"source_url": "https://example.com/report.txt", "doc_type": "report"},
                )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Quote endpoint: Finnhub failure → DB fallback → 404 when DB empty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quote_returns_404_when_finnhub_fails_and_db_empty():
    conn = FakeConn()
    app.dependency_overrides[get_db] = _override(conn)
    try:
        with patch("backend.api.routers.stocks.fetch_finnhub_quote", AsyncMock(return_value=None)), \
             patch("backend.api.routers.stocks.get_ohlcv", AsyncMock(return_value=[])):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/v1/stocks/AAPL/quote", headers=AUTH)
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_quote_returns_db_cache_when_finnhub_fails():
    conn = FakeConn()
    now = datetime.now(tz=timezone.utc)
    fake_row = {"close": 175.5, "timestamp": now}

    app.dependency_overrides[get_db] = _override(conn)
    try:
        with patch("backend.api.routers.stocks.fetch_finnhub_quote", AsyncMock(return_value=None)), \
             patch("backend.api.routers.stocks.get_ohlcv", AsyncMock(return_value=[fake_row])):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/v1/stocks/AAPL/quote", headers=AUTH)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "db_cache"
    assert body["close"] == pytest.approx(175.5)


# ---------------------------------------------------------------------------
# Decision endpoint: cached path + force-recompute path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decision_returns_cached_when_fresh():
    conn = FakeConn()
    now = datetime.now(tz=timezone.utc)
    cached_row = {
        "recommendation": "BUY",
        "confidence": 0.72,
        "risk_level": "Medium",
        "weighted_score": 0.4,
        "signals_json": '{"rsi": 1, "trend": 1}',
        "explanation": "Strong uptrend.",
        "current_close": 180.0,
        "created_at": now,
    }

    app.dependency_overrides[get_db] = _override(conn)
    try:
        with patch("backend.api.routers.decision.get_latest_decision", AsyncMock(return_value=cached_row)), \
             patch("backend.api.routers.decision.get_forecasts", AsyncMock(return_value=[])), \
             patch("backend.api.routers.decision.get_sentiment_history", AsyncMock(return_value=[])), \
             patch("backend.api.routers.decision.get_latest_sentiment", AsyncMock(return_value=None)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/v1/decision/AAPL", headers=AUTH)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["recommendation"] == "BUY"
    assert body["cached"] is True


@pytest.mark.asyncio
async def test_decision_invalid_symbol_returns_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/decision/invalid-ticker!", headers=AUTH)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Manual job trigger
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_job_trigger_unknown_job_returns_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/jobs/trigger/nonexistent_job", headers=AUTH)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_job_trigger_known_job_fires():
    with patch("backend.api.routers.jobs.asyncio.create_task") as mock_task:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/v1/jobs/trigger/sentiment_run", headers=AUTH)
    assert resp.status_code == 202
    mock_task.assert_called_once()
