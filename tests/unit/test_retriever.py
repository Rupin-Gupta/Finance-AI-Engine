import numpy as np
import pytest

from backend.rag import faiss_store
from backend.rag import retriever as retriever_mod
from backend.rag import chain as chain_mod
from backend.db import queries as _  # ensure importable


# --- faiss_store unit tests ---

def test_add_vectors_stamps_index_version(monkeypatch, tmp_path):
    monkeypatch.setattr(faiss_store, "_index", None)
    monkeypatch.setattr(faiss_store, "_metadata", None)
    monkeypatch.setattr(faiss_store, "_loaded_version", 0)

    # Patch paths to tmp dir so save_index doesn't hit real disk
    import faiss as _faiss
    monkeypatch.setattr(faiss_store, "_paths", lambda: (
        tmp_path / "test.index", tmp_path / "test.pkl"
    ))

    vecs = np.random.randn(3, 384).astype("float32")
    meta = [{"doc_id": f"doc-{i}", "chunk_index": i} for i in range(3)]
    faiss_store.add_vectors(vecs, meta, index_version=7)

    assert faiss_store._loaded_version == 7
    assert all(m["index_version"] == 7 for m in faiss_store._metadata)


def test_add_vectors_auto_increments_version(monkeypatch, tmp_path):
    import faiss as _faiss
    # Pre-set a real index so add_vectors doesn't call load_index() and reset _loaded_version
    monkeypatch.setattr(faiss_store, "_index", _faiss.IndexFlatIP(384))
    monkeypatch.setattr(faiss_store, "_metadata", [])
    monkeypatch.setattr(faiss_store, "_loaded_version", 3)
    monkeypatch.setattr(faiss_store, "_paths", lambda: (
        tmp_path / "test2.index", tmp_path / "test2.pkl"
    ))

    vecs = np.random.randn(2, 384).astype("float32")
    meta = [{"doc_id": "doc-x", "chunk_index": i} for i in range(2)]
    faiss_store.add_vectors(vecs, meta)

    assert faiss_store._loaded_version == 4
    assert all(m["index_version"] == 4 for m in faiss_store._metadata)


def test_search_returns_scored_hits(monkeypatch, tmp_path):
    monkeypatch.setattr(faiss_store, "_index", None)
    monkeypatch.setattr(faiss_store, "_metadata", None)
    monkeypatch.setattr(faiss_store, "_loaded_version", 0)
    monkeypatch.setattr(faiss_store, "_paths", lambda: (
        tmp_path / "s.index", tmp_path / "s.pkl"
    ))

    vecs = np.random.randn(5, 384).astype("float32")
    meta = [{"doc_id": f"doc-{i}", "chunk_index": i} for i in range(5)]
    faiss_store.add_vectors(vecs, meta, index_version=1)

    query_vec = np.random.randn(384).astype("float32")
    results = faiss_store.search(query_vec, top_k=3)

    assert len(results) == 3
    for r in results:
        assert "doc_id" in r
        assert "chunk_index" in r
        assert "score" in r
        assert isinstance(r["score"], float)


def test_search_empty_index_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(faiss_store, "_index", None)
    monkeypatch.setattr(faiss_store, "_metadata", None)
    monkeypatch.setattr(faiss_store, "_loaded_version", 0)
    monkeypatch.setattr(faiss_store, "_paths", lambda: (
        tmp_path / "empty.index", tmp_path / "empty.pkl"
    ))

    query_vec = np.random.randn(384).astype("float32")
    results = faiss_store.search(query_vec, top_k=5)
    assert results == []


# --- retrieve() integration ---

def test_retrieve_calls_embed_and_search(monkeypatch):
    fake_vec = np.ones(384, dtype="float32")
    monkeypatch.setattr(retriever_mod, "embed_query", lambda q: fake_vec)

    captured = {}

    def fake_search(vec, top_k):
        captured["vec"] = vec
        captured["top_k"] = top_k
        return [{"doc_id": "d1", "chunk_index": 0, "score": 0.9}]

    monkeypatch.setattr(retriever_mod, "search", fake_search)

    hits = retriever_mod.retrieve("what is revenue?", top_k=3)

    assert captured["top_k"] == 3
    np.testing.assert_array_equal(captured["vec"], fake_vec)
    assert hits == [{"doc_id": "d1", "chunk_index": 0, "score": 0.9}]


# --- chain V2 version mismatch ---

@pytest.mark.asyncio
async def test_chain_raises_on_version_mismatch(monkeypatch):
    monkeypatch.setattr(chain_mod, "get_loaded_version", lambda: 1)

    async def fake_db_version(conn):
        return 2

    monkeypatch.setattr(chain_mod, "get_db_index_version", fake_db_version)

    class FakeConn:
        pass

    with pytest.raises(RuntimeError, match="FAISS index version mismatch"):
        await chain_mod.answer(FakeConn(), "test query")


@pytest.mark.asyncio
async def test_chain_skips_version_check_when_db_empty(monkeypatch):
    monkeypatch.setattr(chain_mod, "get_loaded_version", lambda: 0)

    async def fake_db_version(conn):
        return 0  # no embeddings in DB yet

    monkeypatch.setattr(chain_mod, "get_db_index_version", fake_db_version)
    monkeypatch.setattr(chain_mod, "retrieve", lambda q, top_k: [])

    async def fake_append(conn, query, response, sources, user_id=None):
        return "chat-id"

    monkeypatch.setattr(chain_mod, "append_chat_history", fake_append)

    class FakeConn:
        pass

    result = await chain_mod.answer(FakeConn(), "empty db query")
    assert result["answer"] == "No relevant documents found."
    assert result["sources"] == []
