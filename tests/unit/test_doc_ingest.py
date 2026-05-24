import numpy as np
import pytest

from backend.ingest import doc_pipeline


class FakeConn:
    def __init__(self):
        self.job_updates = []
        self.doc_rows = []
        self.chunk_rows = []

    async def fetchrow(self, query, *args):
        if "INSERT INTO jobs" in query:
            return {"id": "job-doc-1"}
        if "INSERT INTO financial_reports" in query:
            return {"id": "doc-uuid-1"}
        if "MAX(index_version)" in query:
            return {"v": 1}
        raise AssertionError(f"unexpected fetchrow: {query!r}")

    async def execute(self, query, *args):
        assert "UPDATE jobs" in query
        self.job_updates.append(args)

    async def executemany(self, query, rows):
        assert "INSERT INTO embeddings" in query
        self.chunk_rows.extend(rows)


@pytest.mark.asyncio
async def test_run_doc_ingest_full_pipeline(monkeypatch):
    async def fake_fetch(url):
        return "First sentence. Second sentence. Third sentence."

    monkeypatch.setattr(doc_pipeline, "fetch_document_text", fake_fetch)

    fake_vectors = np.ones((1, 384), dtype="float32")
    monkeypatch.setattr(doc_pipeline, "embed_texts", lambda chunks: fake_vectors)

    captured_meta = []

    def fake_add_vectors(vecs, meta, index_version=None):
        captured_meta.extend(meta)

    monkeypatch.setattr(doc_pipeline, "add_vectors", fake_add_vectors)

    conn = FakeConn()
    job_id = await doc_pipeline.run_doc_ingest(conn, "https://example.com/report.txt", "report")

    assert job_id == "job-doc-1"
    assert conn.job_updates == [("completed", None, "job-doc-1")]
    assert len(conn.chunk_rows) == 1
    assert conn.chunk_rows[0][0] == "doc-uuid-1"   # doc_id
    assert conn.chunk_rows[0][1] == 0               # chunk_index
    assert isinstance(conn.chunk_rows[0][3], bytes)  # embedding_vector serialized
    assert captured_meta == [{"doc_id": "doc-uuid-1", "chunk_index": 0}]


@pytest.mark.asyncio
async def test_run_doc_ingest_marks_failed_on_fetch_error(monkeypatch):
    async def bad_fetch(url):
        raise RuntimeError("connection timeout")

    monkeypatch.setattr(doc_pipeline, "fetch_document_text", bad_fetch)

    conn = FakeConn()
    with pytest.raises(RuntimeError, match="connection timeout"):
        await doc_pipeline.run_doc_ingest(conn, "https://bad.example.com/", "report")

    assert conn.job_updates == [("failed", "connection timeout", "job-doc-1")]


@pytest.mark.asyncio
async def test_run_doc_ingest_empty_text_completes_cleanly(monkeypatch):
    async def empty_fetch(url):
        return ""

    monkeypatch.setattr(doc_pipeline, "fetch_document_text", empty_fetch)

    conn = FakeConn()
    job_id = await doc_pipeline.run_doc_ingest(conn, "https://example.com/empty.txt")

    assert job_id == "job-doc-1"
    assert conn.job_updates == [("completed", None, "job-doc-1")]
    assert conn.chunk_rows == []
