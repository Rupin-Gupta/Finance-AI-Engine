from backend.rag.embedder import embed_query
from backend.rag.faiss_store import search


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Embed query → FAISS search → [{doc_id, chunk_index, score}]."""
    vec = embed_query(query)
    return search(vec, top_k=top_k)
