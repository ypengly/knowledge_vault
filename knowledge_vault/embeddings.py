"""Embedders and the vector index.

* HashingEmbedder  - default, dependency-free, fully local. It is a *lexical*
  feature-hashing model (stemmed unigrams + bigrams). It finds related wording,
  not true synonyms. We label it honestly in the UI.
* SentenceTransformerEmbedder - optional, local neural embeddings (true semantic search).
"""
from __future__ import annotations

import threading
import zlib

import numpy as np

from .textutil import stems


class Embedder:
    name = "base"
    dim = 0
    semantic = False  # True only for real neural embeddings

    def embed(self, texts: list[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class HashingEmbedder(Embedder):
    name = "hashing-512"
    dim = 512
    semantic = False

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype="float32")
        for r, t in enumerate(texts):
            st = stems(t)
            feats = st + [f"{a}_{b}" for a, b in zip(st, st[1:])]
            for f in feats:
                h = zlib.crc32(f.encode("utf-8"))
                out[r, h % self.dim] += (1.0 if (h >> 16) & 1 else -1.0)
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return out / norms


class SentenceTransformerEmbedder(Embedder):
    semantic = True

    def __init__(self, model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError("Install 'sentence-transformers' to use neural local embeddings.") from e
        self.model = SentenceTransformer(model_name)
        self.name = f"st:{model_name}"
        self.dim = int(self.model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        v = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(v, dtype="float32")


def make_embedder(kind: str, st_model: str = "") -> Embedder:
    if kind == "sentence_transformers":
        return SentenceTransformerEmbedder(st_model or "all-MiniLM-L6-v2")
    return HashingEmbedder()


class VectorIndex:
    """Inner-product index over normalised vectors. Uses FAISS when installed,
    otherwise an exact NumPy search (identical results, fine for personal scale)."""

    def __init__(self, dim: int):
        self.dim = dim
        self._lock = threading.RLock()
        self._ids = np.zeros(0, dtype="int64")
        self._mat = np.zeros((0, dim), dtype="float32")
        self._faiss = None
        try:
            import faiss  # type: ignore
            self._faiss = faiss
        except Exception:
            pass
        self._findex = None

    @property
    def backend(self) -> str:
        return "FAISS" if self._faiss else "NumPy"

    def __len__(self) -> int:
        return len(self._ids)

    def _rebuild_faiss(self) -> None:
        if self._faiss:
            self._findex = self._faiss.IndexFlatIP(self.dim)
            if len(self._ids):
                self._findex.add(self._mat)

    def reset(self, ids: np.ndarray, mat: np.ndarray) -> None:
        with self._lock:
            self._ids = ids.astype("int64")
            self._mat = mat.astype("float32").reshape(-1, self.dim)
            self._rebuild_faiss()

    def add(self, ids: list[int], mat: np.ndarray) -> None:
        with self._lock:
            self._ids = np.concatenate([self._ids, np.asarray(ids, dtype="int64")])
            self._mat = np.vstack([self._mat, mat.astype("float32")])
            if self._findex is not None:
                self._findex.add(mat.astype("float32"))

    def search(self, qvec: np.ndarray, k: int, allowed: set[int] | None = None) -> list[tuple[int, float]]:
        with self._lock:
            n = len(self._ids)
            if n == 0 or (allowed is not None and not allowed):
                return []
            q = qvec.reshape(1, -1).astype("float32")
            if self._findex is not None and allowed is None:
                scores, idx = self._findex.search(q, min(k, n))
                return [(int(self._ids[i]), float(s)) for s, i in zip(scores[0], idx[0]) if i >= 0]
            sims = (self._mat @ q.T).ravel()
            if allowed is not None:
                mask = np.isin(self._ids, np.fromiter(allowed, dtype="int64"))
                sims = np.where(mask, sims, -np.inf)
            order = np.argsort(-sims)[:k]
            return [(int(self._ids[i]), float(sims[i])) for i in order if np.isfinite(sims[i])]
