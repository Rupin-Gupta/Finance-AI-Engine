"""T15: Integration tests — ETL roundtrip, RAG Q&A, anomaly trigger, auth rejection."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.dependencies import get_db
from backend.config import settings

API_KEY = settings.api_key
AUTH = {"X-API-Key": API_KEY}


# ---------------------------------------------------------------------------
# Shared fake DB connection factory
# ---------------------------------------------------------------------------

class FakeConn:
    """Fake asyncpg connection. Tracks writes; job queries return a stable id."""

    def __init__(self, job_id: str = "test-job-1"):
        self._job_id = job_id
        self.inserted_market_rows: list = []
        self.inserted_stock_rows: list = []
        self.inserted_alert_rows: list = []
        self.job_updates: list = []
        self.chat_rows: list = []
        self._fetch_returns: list = []  # per-call queue for fetch()

    async def fetchrow(self, query: str, *args):
        if "INSERT INTO jobs" in query:
            return {"id": self._job_id}
        if "INSERT INTO alerts" in query:
            self.inserted_alert_rows.append(args)
            return {"id": "alert-1"}
        if "INSERT INTO chat_history" in query:
            self.chat_rows.append(args)
            return {"id": "chat-1"}
        return None

    async def execute(self, query: str, *args):
        if "UPDATE jobs" in query:
            self.job_updates.append(args)

    async def executemany(self, query: str, rows):
        if "INSERT INTO stocks" in query:
            self.inserted_stock_rows.extend(rows)
        elif "INSERT INTO market_data" in query:
            self.inserted_market_rows.extend(rows)

    async def fetch(self, query: str, *args):
        if self._fetch_returns:
            return self._fetch_returns.pop(0)
        return []


def _override_get_db(conn: FakeConn):
    """Return a FastAPI dependency override that yields conn."""
    async def _dep():
        yield conn
    return _dep


# ---------------------------------------------------------------------------
# V6 — Auth rejection (no key / wrong key → 401)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_no_key_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/ingest/market", json={"symbols": ["AAPL"]})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_wrong_key_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/ingest/market",
            json={"symbols": ["AAPL"]},
            headers={"X-API-Key": "totallywrong"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_correct_key_passes_through():
    conn = FakeConn("job-auth-ok")

    async def fake_ingest(c, symbols, period, interval):
        return "job-auth-ok"

    app.dependency_overrides[get_db] = _override_get_db(conn)
    try:
        with patch("backend.api.routers.ingest.run_market_ingest", side_effect=fake_ingest):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/ingest/market",
                    json={"symbols": ["AAPL"]},
                    headers=AUTH,
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["job_id"] == "job-auth-ok"


# ---------------------------------------------------------------------------
# V7/V8/V11 — ETL roundtrip: POST /v1/ingest/market → job_id, market rows written
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_etl_roundtrip_returns_job_id_and_writes_market_rows():
    conn = FakeConn("job-etl-1")
    ts = datetime(2026, 1, 2, tzinfo=timezone.utc)

    async def fake_fetch_ohlcv(symbol, period, interval):
        return [
            {"symbol": "AAPL", "timestamp": ts,
             "open": 150.0, "high": 155.0, "low": 148.0, "close": 153.0, "volume": 50000},
        ]

    app.dependency_overrides[get_db] = _override_get_db(conn)
    try:
        with patch("backend.ingest.pipeline.fetch_ohlcv", side_effect=fake_fetch_ohlcv):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/ingest/market",
                    json={"symbols": ["AAPL"], "period": "5d", "interval": "1d"},
                    headers=AUTH,
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["job_id"] == "job-etl-1"
    # V8: job row created
    assert ("AAPL",) in conn.inserted_stock_rows
    # V7: market row upserted
    assert len(conn.inserted_market_rows) == 1
    row = conn.inserted_market_rows[0]
    assert row[0] == "AAPL"
    assert row[4] == 148.0  # low


@pytest.mark.asyncio
async def test_etl_roundtrip_idempotent_on_duplicate_symbol_timestamp():
    """Same (symbol, timestamp) twice → deduped to 1 row (V7)."""
    conn = FakeConn("job-etl-2")
    ts = datetime(2026, 1, 2, tzinfo=timezone.utc)

    async def fake_fetch_ohlcv(symbol, period, interval):
        return [
            {"symbol": "AAPL", "timestamp": ts,
             "open": 150.0, "high": 155.0, "low": 148.0, "close": 153.0, "volume": 50000},
            {"symbol": "AAPL", "timestamp": ts,  # duplicate
             "open": 151.0, "high": 156.0, "low": 149.0, "close": 154.0, "volume": 60000},
        ]

    app.dependency_overrides[get_db] = _override_get_db(conn)
    try:
        with patch("backend.ingest.pipeline.fetch_ohlcv", side_effect=fake_fetch_ohlcv):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await client.post(
                    "/v1/ingest/market",
                    json={"symbols": ["AAPL"]},
                    headers=AUTH,
                )
    finally:
        app.dependency_overrides.clear()

    assert len(conn.inserted_market_rows) == 1  # deduped


@pytest.mark.asyncio
async def test_etl_roundtrip_marks_job_failed_on_null_field():
    """V11: null required OHLCV field → job status=failed, error recorded."""
    from backend.ingest.pipeline import run_market_ingest
    conn = FakeConn("job-etl-fail")
    ts = datetime(2026, 1, 2, tzinfo=timezone.utc)

    async def fake_fetch_ohlcv(symbol, period, interval):
        return [
            {"symbol": "AAPL", "timestamp": ts,
             "open": 150.0, "high": 155.0, "low": 148.0, "close": None, "volume": 50000},
        ]

    with patch("backend.ingest.pipeline.fetch_ohlcv", side_effect=fake_fetch_ohlcv):
        with pytest.raises(ValueError, match="null required fields"):
            await run_market_ingest(conn, ["AAPL"])

    assert conn.job_updates == [("failed", "OHLCV row contains null required fields", "job-etl-fail")]


# ---------------------------------------------------------------------------
# V3 — RAG Q&A with citations
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rag_query_returns_answer_and_sources():
    """POST /v1/query → {answer, sources[{doc_id,chunk_id,score}]} (V3)."""
    conn = FakeConn()
    hits = [{"doc_id": "doc-1", "chunk_index": 0, "score": 0.92}]
    chunk_records = [{"text": "Revenue grew 12% YoY."}]

    with patch("backend.rag.chain.get_db_index_version", AsyncMock(return_value=0)), \
         patch("backend.rag.chain.get_loaded_version", return_value=0), \
         patch("backend.rag.chain.retrieve", return_value=hits), \
         patch("backend.rag.chain.get_chunk_texts", AsyncMock(return_value=chunk_records)), \
         patch("backend.rag.chain.append_chat_history", AsyncMock()):

        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value="Revenue grew 12% YoY.")
        with patch("backend.rag.chain.get_llm_client", return_value=mock_llm):
            app.dependency_overrides[get_db] = _override_get_db(conn)
            try:
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post(
                        "/v1/query",
                        json={"query": "What is revenue trend?", "top_k": 5},
                        headers=AUTH,
                    )
            finally:
                app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Revenue grew 12% YoY."
    assert len(body["sources"]) == 1
    src = body["sources"][0]
    assert src["doc_id"] == "doc-1"
    assert src["chunk_id"] == 0
    assert src["score"] == pytest.approx(0.92)


@pytest.mark.asyncio
async def test_rag_query_returns_empty_sources_when_no_hits():
    """No FAISS hits → answer='No relevant documents found.', sources=[] (V3)."""
    conn = FakeConn()

    with patch("backend.rag.chain.get_db_index_version", AsyncMock(return_value=0)), \
         patch("backend.rag.chain.get_loaded_version", return_value=0), \
         patch("backend.rag.chain.retrieve", return_value=[]), \
         patch("backend.rag.chain.append_chat_history", AsyncMock()):

        app.dependency_overrides[get_db] = _override_get_db(conn)
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    "/v1/query",
                    json={"query": "unknown topic", "top_k": 5},
                    headers=AUTH,
                )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"] == []
    assert "No relevant" in body["answer"]


@pytest.mark.asyncio
async def test_rag_query_v2_version_mismatch_raises():
    """V2: loaded FAISS version ≠ DB version → RuntimeError raised."""
    from backend.rag.chain import answer as rag_answer
    conn = FakeConn()

    with patch("backend.rag.chain.get_db_index_version", AsyncMock(return_value=3)), \
         patch("backend.rag.chain.get_loaded_version", return_value=1):
        with pytest.raises(RuntimeError, match="FAISS index version mismatch"):
            await rag_answer(conn, "anything", top_k=5)


# ---------------------------------------------------------------------------
# V9 — Anomaly trigger: spike data → alert written
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anomaly_scan_spike_writes_alert_and_job_row():
    """Z-score spike → alert row written (V9) + job row (V8)."""
    from datetime import timedelta
    import pandas as pd
    from backend.scheduler.jobs.anomaly_scan import run as anomaly_run
    from backend.analytics.anomaly import zscore_anomalies

    conn = FakeConn("job-anomaly-1")

    # Normal prices + one huge spike that exceeds z=3
    base_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    normal_rows = [
        {"symbol": "AAPL", "timestamp": base_ts + timedelta(days=i),
         "open": 150.0, "high": 152.0, "low": 149.0, "close": 150.0 + i * 0.01, "volume": 1_000_000}
        for i in range(30)
    ]
    spike_row = {
        "symbol": "AAPL", "timestamp": base_ts + timedelta(days=30),
        "open": 500.0, "high": 600.0, "low": 490.0, "close": 999.0, "volume": 1_000_000,
    }
    all_rows = normal_rows + [spike_row]

    fake_records = [MagicMock(**{k: v for k, v in r.items()}, **{"__getitem__": lambda s, k: r[k]}) for r in all_rows]
    for rec, row in zip(fake_records, all_rows):
        rec.__iter__ = lambda s, r=row: iter(r.items())
        # make dict(r) work
        rec.keys = lambda r=row: r.keys()
        rec.__getitem__ = lambda s, k, r=row: r[k]
        rec.items = lambda r=row: r.items()

    # Use real zscore_anomalies but mock DB fetch + pool
    pool_cm = MagicMock()
    pool_cm.__aenter__ = AsyncMock(return_value=conn)
    pool_cm.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=pool_cm)

    # Return proper dict-like records via pandas-compatible path
    real_rows = [dict(r) for r in all_rows]

    with patch("backend.scheduler.jobs.anomaly_scan.get_db_pool", AsyncMock(return_value=mock_pool)), \
         patch("backend.scheduler.jobs.anomaly_scan.get_ohlcv", AsyncMock(return_value=real_rows)), \
         patch("backend.scheduler.jobs.anomaly_scan.insert_alert", AsyncMock(return_value="alert-spike")) as mock_alert:
        await anomaly_run()

    # job completed
    assert conn.job_updates == [("completed", None, "job-anomaly-1")]
    # alert written for spike
    mock_alert.assert_awaited()


@pytest.mark.asyncio
async def test_anomaly_scan_no_anomalies_writes_no_alerts():
    """Flat price series → no alerts written."""
    from datetime import timedelta
    from backend.scheduler.jobs.anomaly_scan import run as anomaly_run

    conn = FakeConn("job-anomaly-2")

    base_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    flat_rows = [
        {"symbol": "AAPL", "timestamp": base_ts + timedelta(days=i),
         "open": 150.0, "high": 151.0, "low": 149.0, "close": 150.0, "volume": 1_000_000}
        for i in range(30)
    ]

    pool_cm = MagicMock()
    pool_cm.__aenter__ = AsyncMock(return_value=conn)
    pool_cm.__aexit__ = AsyncMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.acquire = MagicMock(return_value=pool_cm)

    with patch("backend.scheduler.jobs.anomaly_scan.get_db_pool", AsyncMock(return_value=mock_pool)), \
         patch("backend.scheduler.jobs.anomaly_scan.get_ohlcv", AsyncMock(return_value=flat_rows)), \
         patch("backend.scheduler.jobs.anomaly_scan.insert_alert", AsyncMock()) as mock_alert:
        await anomaly_run()

    mock_alert.assert_not_awaited()
    assert conn.job_updates == [("completed", None, "job-anomaly-2")]


# ---------------------------------------------------------------------------
# V6 — All protected endpoints reject missing/wrong key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,body", [
    ("GET",  "/v1/alerts",              None),
    ("GET",  "/v1/reports",             None),
    ("POST", "/v1/query",               {"query": "x", "top_k": 1}),
    ("POST", "/v1/ingest/market",       {"symbols": ["AAPL"]}),
    ("POST", "/v1/ingest/docs",         {"source_url": "http://x.com/f.txt"}),
    ("GET",  "/v1/analytics/AAPL",      None),
])
@pytest.mark.asyncio
async def test_all_protected_endpoints_reject_missing_key(method, path, body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        fn = client.get if method == "GET" else client.post
        kwargs = {}
        if body:
            kwargs["json"] = body
        resp = await fn(path, **kwargs)
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path,body", [
    ("GET",  "/v1/alerts",              None),
    ("GET",  "/v1/reports",             None),
    ("POST", "/v1/query",               {"query": "x", "top_k": 1}),
    ("POST", "/v1/ingest/market",       {"symbols": ["AAPL"]}),
    ("POST", "/v1/ingest/docs",         {"source_url": "http://x.com/f.txt"}),
    ("GET",  "/v1/analytics/AAPL",      None),
])
@pytest.mark.asyncio
async def test_all_protected_endpoints_reject_wrong_key(method, path, body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        fn = client.get if method == "GET" else client.post
        kwargs = {"headers": {"X-API-Key": "badkey"}}
        if body:
            kwargs["json"] = body
        resp = await fn(path, **kwargs)
    assert resp.status_code == 401
