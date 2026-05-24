import os
import pickle
import threading
from pathlib import Path

import faiss
import numpy as np

from backend.config import settings

_index: faiss.Index | None = None
_metadata: list[dict] | None = None
_loaded_version: int = 0
_lock = threading.Lock()


def _paths() -> tuple[Path, Path]:
    return Path(settings.faiss_index_path), Path(settings.faiss_metadata_path)


def load_index() -> tuple[faiss.Index, list[dict]]:
    global _index, _metadata, _loaded_version
    with _lock:
        idx_path, meta_path = _paths()
        if idx_path.exists() and meta_path.exists():
            _index = faiss.read_index(str(idx_path))
            with open(meta_path, "rb") as f:
                _metadata = pickle.load(f)
            _loaded_version = max((m.get("index_version", 0) for m in _metadata), default=0)
        else:
            _index = faiss.IndexFlatIP(384)
            _metadata = []
            _loaded_version = 0
        return _index, _metadata


def get_loaded_version() -> int:
    with _lock:
        return _loaded_version


def _save_index_unsafe() -> None:
    """Must be called with _lock held."""
    idx_path, meta_path = _paths()
    idx_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_idx = idx_path.with_suffix(".tmp")
    tmp_meta = meta_path.with_suffix(".tmp")

    faiss.write_index(_index, str(tmp_idx))
    with open(tmp_meta, "wb") as f:
        pickle.dump(_metadata, f)

    os.replace(tmp_idx, idx_path)
    os.replace(tmp_meta, meta_path)


def save_index() -> None:
    with _lock:
        _save_index_unsafe()


def add_vectors(vectors: np.ndarray, meta: list[dict], index_version: int | None = None) -> None:
    global _index, _metadata, _loaded_version
    with _lock:
        if _index is None:
            idx_path, meta_path = _paths()
            if idx_path.exists() and meta_path.exists():
                _index = faiss.read_index(str(idx_path))
                with open(meta_path, "rb") as f:
                    _metadata = pickle.load(f)
                _loaded_version = max((m.get("index_version", 0) for m in _metadata), default=0)
            else:
                _index = faiss.IndexFlatIP(384)
                _metadata = []
                _loaded_version = 0
        new_version = index_version if index_version is not None else _loaded_version + 1
        stamped = [{**m, "index_version": new_version} for m in meta]
        _index.add(vectors.astype("float32"))
        _metadata.extend(stamped)
        _loaded_version = new_version
        _save_index_unsafe()


def search(query_vec: np.ndarray, top_k: int = 5) -> list[dict]:
    """Returns [{doc_id, chunk_index, score}]."""
    with _lock:
        if _index is None:
            idx_path, meta_path = _paths()
            if idx_path.exists() and meta_path.exists():
                _index = faiss.read_index(str(idx_path))
                with open(meta_path, "rb") as f:
                    _metadata = pickle.load(f)
                _loaded_version = max((m.get("index_version", 0) for m in _metadata), default=0)
            else:
                _index = faiss.IndexFlatIP(384)
                _metadata = []
        if _index.ntotal == 0:
            return []
        scores, indices = _index.search(query_vec.reshape(1, -1).astype("float32"), top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            entry = dict(_metadata[idx])
            entry["score"] = float(score)
            results.append(entry)
        return results
