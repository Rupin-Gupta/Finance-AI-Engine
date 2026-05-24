import asyncpg

from backend.rag.retriever import retrieve
from backend.rag.faiss_store import get_loaded_version
from backend.db.queries.documents import get_chunk_texts, get_db_index_version
from backend.llm.client import get_llm_client
from backend.llm.prompts import build_rag_prompt
from backend.db.queries.chat import append_chat_history


async def answer(conn: asyncpg.Connection, query: str,
                 top_k: int = 5) -> dict:
    """RAG chain: query → FAISS → DB chunks → LLM → {answer, sources}."""
    # V2: verify loaded FAISS index version matches DB
    db_version = await get_db_index_version(conn)
    if db_version > 0 and get_loaded_version() != db_version:
        raise RuntimeError(
            f"FAISS index version mismatch: loaded={get_loaded_version()} db={db_version}. "
            "Delete index files and re-run POST /v1/ingest/docs."
        )

    hits = retrieve(query, top_k=top_k)
    if not hits:
        result = {"answer": "No relevant documents found.", "sources": []}
        await append_chat_history(conn, query, result["answer"], [])
        return result

    doc_ids = [h["doc_id"] for h in hits]
    chunk_ids = [h["chunk_index"] for h in hits]
    chunk_records = await get_chunk_texts(conn, doc_ids, chunk_ids)

    context_parts = [r["text"] for r in chunk_records]
    prompt = build_rag_prompt(query, context_parts)

    client = get_llm_client()
    answer_text = await client.complete(prompt)

    sources = [{"doc_id": h["doc_id"], "chunk_id": h["chunk_index"], "score": h["score"]}
               for h in hits]
    await append_chat_history(conn, query, answer_text, sources)
    return {"answer": answer_text, "sources": sources}
