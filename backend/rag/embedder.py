import numpy as np
from sentence_transformers import SentenceTransformer

from backend.config import settings

_model: SentenceTransformer | None = None
_EMBED_BATCH_SIZE = 64


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    model = get_model()
    batches = [
        model.encode(texts[i:i + _EMBED_BATCH_SIZE], normalize_embeddings=True, show_progress_bar=False)
        for i in range(0, len(texts), _EMBED_BATCH_SIZE)
    ]
    return np.vstack(batches) if len(batches) > 1 else batches[0]


def embed_query(query: str) -> np.ndarray:
    return get_model().encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
