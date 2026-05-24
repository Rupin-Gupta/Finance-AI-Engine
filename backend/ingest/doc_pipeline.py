import numpy as np
import asyncpg

from backend.ingest.documents import fetch_document_text
from backend.rag.chunker import chunk_text
from backend.rag.embedder import embed_texts
from backend.rag.faiss_store import add_vectors
from backend.db.queries.documents import upsert_document, upsert_chunks
from backend.db.queries.jobs import create_job, update_job_status


async def run_text_ingest(
    conn: asyncpg.Connection,
    text: str,
    source_url: str,
    doc_type: str = "report",
) -> str:
    """Chunk + embed pre-extracted text → upsert DB + FAISS. Returns job_id."""
    job_id = await create_job(conn, "doc_ingest")
    try:
        chunks = chunk_text(text)
        if not chunks:
            await update_job_status(conn, job_id, "completed")
            return job_id
        vectors: np.ndarray = embed_texts(chunks)
        doc_id = await upsert_document(conn, source_url, doc_type, len(chunks))
        chunk_records = [
            {
                "chunk_index": i,
                "text": chunk,
                "embedding_vector": vectors[i].astype("float32").tobytes(),
            }
            for i, chunk in enumerate(chunks)
        ]
        await upsert_chunks(conn, doc_id, chunk_records)
        meta = [{"doc_id": doc_id, "chunk_index": i} for i in range(len(chunks))]
        add_vectors(vectors.astype("float32"), meta)
        await update_job_status(conn, job_id, "completed")
    except Exception as exc:
        await update_job_status(conn, job_id, "failed", error=str(exc))
        raise
    return job_id


async def run_doc_ingest(
    conn: asyncpg.Connection,
    source_url: str,
    doc_type: str = "report",
) -> str:
    """Fetch URL → chunk → embed → upsert DB + FAISS. Returns job_id."""
    job_id = await create_job(conn, "doc_ingest")
    try:
        text = await fetch_document_text(source_url)
        chunks = chunk_text(text)
        if not chunks:
            await update_job_status(conn, job_id, "completed")
            return job_id

        vectors: np.ndarray = embed_texts(chunks)

        doc_id = await upsert_document(conn, source_url, doc_type, len(chunks))

        chunk_records = [
            {
                "chunk_index": i,
                "text": chunk,
                "embedding_vector": vectors[i].astype("float32").tobytes(),
            }
            for i, chunk in enumerate(chunks)
        ]
        await upsert_chunks(conn, doc_id, chunk_records)

        meta = [{"doc_id": doc_id, "chunk_index": i} for i in range(len(chunks))]
        add_vectors(vectors.astype("float32"), meta)

        await update_job_status(conn, job_id, "completed")
    except Exception as exc:
        await update_job_status(conn, job_id, "failed", error=str(exc))
        raise
    return job_id
