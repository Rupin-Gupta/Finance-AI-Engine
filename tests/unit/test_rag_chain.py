import pytest
from backend.rag import chain as chain_mod


# Shared helpers

def _make_conn(db_version=1, chat_ids=None):
    """Minimal fake connection for chain tests."""
    chat_log = []

    class FakeConn:
        async def fetchrow(self, query, *args):
            if "MAX(index_version)" in query:
                return {"v": db_version}
            if "INSERT INTO chat_history" in query:
                return {"id": "chat-1"}
            raise AssertionError(f"unexpected fetchrow: {query!r}")

        async def fetch(self, query, *args):
            # get_chunk_texts
            if "embeddings" in query:
                return [
                    {"doc_id": "doc-1", "chunk_index": 0, "text": "Revenue grew 12% YoY."},
                    {"doc_id": "doc-2", "chunk_index": 1, "text": "Operating margin improved."},
                ]
            raise AssertionError(f"unexpected fetch: {query!r}")

        async def execute(self, query, *args):
            pass

    return FakeConn(), chat_log


# --- happy path ---

@pytest.mark.asyncio
async def test_answer_happy_path_v3_shape(monkeypatch):
    """Full path: hits → chunks → LLM → V3 {answer, sources}."""
    monkeypatch.setattr(chain_mod, "get_loaded_version", lambda: 1)
    monkeypatch.setattr(chain_mod, "retrieve", lambda q, top_k: [
        {"doc_id": "doc-1", "chunk_index": 0, "score": 0.92},
        {"doc_id": "doc-2", "chunk_index": 1, "score": 0.85},
    ])

    chat_written = []

    async def fake_append(conn, query, response, sources, user_id=None):
        chat_written.append({"query": query, "response": response, "sources": sources})
        return "chat-1"

    monkeypatch.setattr(chain_mod, "append_chat_history", fake_append)

    class FakeLLM:
        async def complete(self, prompt: str) -> str:
            assert "Revenue grew 12% YoY." in prompt
            assert "Operating margin improved." in prompt
            return "Revenue increased 12% year-over-year with improved margins."

    monkeypatch.setattr(chain_mod, "get_llm_client", lambda: FakeLLM())

    conn, _ = _make_conn(db_version=1)
    result = await chain_mod.answer(conn, "What is revenue trend?", top_k=2)

    # V3: shape
    assert "answer" in result
    assert "sources" in result
    assert isinstance(result["answer"], str)
    assert len(result["answer"]) > 0
    assert len(result["sources"]) == 2

    # V3: source fields
    for src in result["sources"]:
        assert "doc_id" in src
        assert "chunk_id" in src
        assert "score" in src

    # V12: chat history written
    assert len(chat_written) == 1
    assert chat_written[0]["query"] == "What is revenue trend?"
    assert chat_written[0]["response"] == result["answer"]
    assert chat_written[0]["sources"] == result["sources"]


@pytest.mark.asyncio
async def test_answer_sources_map_correctly(monkeypatch):
    """Sources list preserves doc_id, chunk_id, score from FAISS hits."""
    monkeypatch.setattr(chain_mod, "get_loaded_version", lambda: 2)

    hits = [
        {"doc_id": "aaa", "chunk_index": 3, "score": 0.77},
        {"doc_id": "bbb", "chunk_index": 0, "score": 0.61},
    ]
    monkeypatch.setattr(chain_mod, "retrieve", lambda q, top_k: hits)
    monkeypatch.setattr(chain_mod, "get_llm_client", lambda: _stub_llm("answer"))
    monkeypatch.setattr(chain_mod, "append_chat_history", _noop_append)

    class Conn:
        async def fetchrow(self, q, *a):
            if "MAX(index_version)" in q:
                return {"v": 2}
            if "chat_history" in q:
                return {"id": "x"}
            raise AssertionError(q)

        async def fetch(self, q, *a):
            return [
                {"doc_id": "aaa", "chunk_index": 3, "text": "chunk A"},
                {"doc_id": "bbb", "chunk_index": 0, "text": "chunk B"},
            ]

    result = await chain_mod.answer(Conn(), "query", top_k=2)

    assert result["sources"] == [
        {"doc_id": "aaa", "chunk_id": 3, "score": 0.77},
        {"doc_id": "bbb", "chunk_id": 0, "score": 0.61},
    ]


# --- no hits ---

@pytest.mark.asyncio
async def test_answer_no_hits_returns_no_docs_message(monkeypatch):
    monkeypatch.setattr(chain_mod, "get_loaded_version", lambda: 1)
    monkeypatch.setattr(chain_mod, "retrieve", lambda q, top_k: [])

    chat_written = []

    async def fake_append(conn, query, response, sources, user_id=None):
        chat_written.append(response)
        return "chat-1"

    monkeypatch.setattr(chain_mod, "append_chat_history", fake_append)

    conn, _ = _make_conn(db_version=1)
    result = await chain_mod.answer(conn, "obscure query")

    assert result == {"answer": "No relevant documents found.", "sources": []}
    assert chat_written == ["No relevant documents found."]


# --- empty chunk records ---

@pytest.mark.asyncio
async def test_answer_empty_chunk_records_sends_empty_context(monkeypatch):
    """FAISS has hits but DB returned no chunk text — LLM gets empty context, still responds."""
    monkeypatch.setattr(chain_mod, "get_loaded_version", lambda: 1)
    monkeypatch.setattr(chain_mod, "retrieve", lambda q, top_k: [
        {"doc_id": "doc-1", "chunk_index": 0, "score": 0.8},
    ])
    monkeypatch.setattr(chain_mod, "append_chat_history", _noop_append)

    prompts_seen = []

    class FakeLLM:
        async def complete(self, prompt: str) -> str:
            prompts_seen.append(prompt)
            return "Insufficient context."

    monkeypatch.setattr(chain_mod, "get_llm_client", lambda: FakeLLM())

    class Conn:
        async def fetchrow(self, q, *a):
            if "MAX(index_version)" in q:
                return {"v": 1}
            if "chat_history" in q:
                return {"id": "x"}
        async def fetch(self, q, *a):
            return []  # no chunks found

    result = await chain_mod.answer(Conn(), "anything")

    assert result["answer"] == "Insufficient context."
    assert len(prompts_seen) == 1
    # prompt built with empty context list — should still be a string
    assert isinstance(prompts_seen[0], str)


# --- LLM error propagates ---

@pytest.mark.asyncio
async def test_answer_llm_error_propagates(monkeypatch):
    monkeypatch.setattr(chain_mod, "get_loaded_version", lambda: 1)
    monkeypatch.setattr(chain_mod, "retrieve", lambda q, top_k: [
        {"doc_id": "doc-1", "chunk_index": 0, "score": 0.9},
    ])
    monkeypatch.setattr(chain_mod, "append_chat_history", _noop_append)

    class BrokenLLM:
        async def complete(self, prompt: str) -> str:
            raise ConnectionError("LLM API unreachable")

    monkeypatch.setattr(chain_mod, "get_llm_client", lambda: BrokenLLM())

    conn, _ = _make_conn(db_version=1)

    with pytest.raises(ConnectionError, match="LLM API unreachable"):
        await chain_mod.answer(conn, "test")


# --- top_k forwarded ---

@pytest.mark.asyncio
async def test_answer_forwards_top_k(monkeypatch):
    monkeypatch.setattr(chain_mod, "get_loaded_version", lambda: 0)

    captured = {}

    def fake_retrieve(q, top_k):
        captured["top_k"] = top_k
        return []

    monkeypatch.setattr(chain_mod, "retrieve", fake_retrieve)
    monkeypatch.setattr(chain_mod, "append_chat_history", _noop_append)

    conn, _ = _make_conn(db_version=0)
    await chain_mod.answer(conn, "q", top_k=7)

    assert captured["top_k"] == 7


# --- helpers ---

def _stub_llm(text: str):
    class _LLM:
        async def complete(self, prompt):
            return text
    return _LLM()


async def _noop_append(conn, query, response, sources, user_id=None):
    return "chat-1"
