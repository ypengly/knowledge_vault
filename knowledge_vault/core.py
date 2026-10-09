"""Vault: the single facade the UI (and tests) talk to."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import qa as qa_mod
from .config import Settings, data_dir
from .db import Database
from .embeddings import Embedder, VectorIndex, make_embedder
from .llm import Provider, make_provider
from .search import Filters, Hit, search


class Vault:
    def __init__(self, directory: Path | None = None, settings: Settings | None = None,
                 embedder: Embedder | None = None):
        self.dir = Path(directory) if directory else data_dir()
        self.files_dir = self.dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.settings = settings or Settings.load(self.dir)
        self.db = Database(self.dir / "vault.db")
        self.set_embedder(embedder or make_embedder(self.settings.embedder, self.settings.st_model))

    # ---- indexing
    def set_embedder(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self.index = VectorIndex(embedder.dim)
        if self.db.get_meta("embedder") not in ("", embedder.name):
            self.reindex()
        else:
            self.db.set_meta("embedder", embedder.name)
            self.load_index()

    def load_index(self) -> None:
        rows = self.db.q("SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL")
        ids = np.array([r["id"] for r in rows], dtype="int64")
        mat = (np.vstack([np.frombuffer(r["embedding"], dtype="float32") for r in rows])
               if rows else np.zeros((0, self.embedder.dim), "float32"))
        if mat.shape[1:] != (self.embedder.dim,):
            self.reindex()
            return
        self.index.reset(ids, mat)

    def reindex(self, progress=None) -> None:
        """Re-embed every chunk (needed when the embedding model changes)."""
        rows = self.db.q("SELECT id, text FROM chunks ORDER BY id")
        ids, mats = [], []
        for start in range(0, len(rows), 64):
            batch = rows[start:start + 64]
            v = self.embedder.embed([r["text"] for r in batch])
            with self.db.conn:
                self.db.conn.executemany("UPDATE chunks SET embedding=? WHERE id=?",
                                         [(x.tobytes(), r["id"]) for x, r in zip(v, batch)])
            ids += [r["id"] for r in batch]; mats.append(v)
            if progress:
                progress(min(start + 64, len(rows)), len(rows))
        self.index.reset(np.array(ids, dtype="int64"),
                         np.vstack(mats) if mats else np.zeros((0, self.embedder.dim), "float32"))
        self.db.set_meta("embedder", self.embedder.name)

    def delete_document(self, doc_id: int) -> None:
        path = self.db.delete_document(doc_id)
        if path:
            Path(path).unlink(missing_ok=True)
        self.load_index()

    # ---- search / ask
    def search(self, query: str, mode: str = "hybrid", filters: Filters | None = None,
               limit: int = 20, log: bool = True) -> list[Hit]:
        if log and query.strip():
            self.db.log_search(query.strip(), mode)
        return search(self, query, mode, filters, limit)

    def provider(self) -> Provider | None:
        return make_provider(self.settings)

    def ask(self, question: str, filters: Filters | None = None, allow_external: bool = False,
            llm: Provider | None = None, use_llm: bool = True) -> qa_mod.Answer:
        if llm is None and use_llm:
            llm = self.provider()
        return qa_mod.ask(self, question, llm, filters, allow_external)

    # ---- privacy banner
    def privacy_status(self) -> tuple[str, bool]:
        """(human text, is_external)"""
        emb = ("local neural embeddings" if self.embedder.semantic else "local lexical index")
        try:
            p = self.provider()
        except Exception:
            p = None
        if p is None:
            return f"100% local — {emb}, no AI model, nothing leaves this computer.", False
        if p.is_external:
            return (f"External AI: {p.label()}. Only the top matching passages are sent, "
                    f"and only after you confirm each question. Indexing stays local."), True
        return f"Local — {emb}; answers by {p.label()}. Nothing leaves this computer.", False

    # ---- pages for the viewer
    def pages(self, doc_id: int):
        return self.db.q("SELECT num, label, text FROM pages WHERE doc_id=? ORDER BY num", (doc_id,))
