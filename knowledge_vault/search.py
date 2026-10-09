"""Keyword (FTS5/BM25), semantic (vector) and hybrid (RRF) search with filters."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .textutil import coverage, tokens


@dataclass
class Filters:
    collection_id: int | None = None
    file_types: list[str] | None = None
    date_from: str | None = None   # YYYY-MM-DD (inclusive)
    date_to: str | None = None     # YYYY-MM-DD (inclusive)
    doc_ids: list[int] | None = None

    def active(self) -> bool:
        return any([self.collection_id, self.file_types, self.date_from, self.date_to, self.doc_ids])


@dataclass
class Hit:
    chunk_id: int
    doc_id: int
    filename: str
    file_type: str
    page: int
    label: str
    text: str
    score: float
    coverage: float = 0.0
    cosine: float = 0.0


def _where(f: Filters | None) -> tuple[str, list]:
    sql, args = " d.status='ready'", []
    if not f:
        return sql, args
    if f.collection_id:
        sql += " AND d.id IN (SELECT doc_id FROM doc_collections WHERE coll_id=?)"
        args.append(f.collection_id)
    if f.file_types:
        sql += f" AND d.file_type IN ({','.join('?' * len(f.file_types))})"
        args += list(f.file_types)
    if f.date_from:
        sql += " AND substr(d.imported_at,1,10) >= ?"
        args.append(f.date_from)
    if f.date_to:
        sql += " AND substr(d.imported_at,1,10) <= ?"
        args.append(f.date_to)
    if f.doc_ids:
        sql += f" AND d.id IN ({','.join('?' * len(f.doc_ids))})"
        args += list(f.doc_ids)
    return sql, args


def _keyword_ids(vault, query: str, f: Filters | None, limit: int) -> list[tuple[int, float]]:
    terms = list(dict.fromkeys(tokens(query)))
    if not terms:
        return []
    match = " OR ".join(f'"{t}"' for t in terms)
    where, args = _where(f)
    rows = vault.db.q(
        "SELECT c.id AS id, bm25(chunks_fts) AS s FROM chunks_fts "
        "JOIN chunks c ON c.id=chunks_fts.rowid JOIN documents d ON d.id=c.doc_id "
        f"WHERE chunks_fts MATCH ? AND {where} ORDER BY s LIMIT ?", (match, *args, limit))
    return [(r["id"], -float(r["s"])) for r in rows]


def _semantic_ids(vault, query: str, f: Filters | None, limit: int) -> list[tuple[int, float]]:
    if not tokens(query):
        return []
    allowed = None
    if f and f.active():
        where, args = _where(f)
        allowed = {r["id"] for r in vault.db.q(
            f"SELECT c.id FROM chunks c JOIN documents d ON d.id=c.doc_id WHERE {where}", args)}
    qv = vault.embedder.embed([query])[0]
    floor = 0.2 if vault.embedder.semantic else 0.05  # never return unrelated nearest-neighbours
    return [(i, s) for i, s in vault.index.search(qv, limit, allowed) if s > floor]


def _build_hits(vault, query: str, ranked: list[tuple[int, float]]) -> list[Hit]:
    if not ranked:
        return []
    ids = [i for i, _ in ranked]
    rows = {r["id"]: r for r in vault.db.q(
        "SELECT c.id, c.doc_id, c.page, c.label, c.text, c.embedding, d.filename, d.file_type "
        f"FROM chunks c JOIN documents d ON d.id=c.doc_id WHERE c.id IN ({','.join('?' * len(ids))})", ids)}
    qv = vault.embedder.embed([query])[0]
    hits = []
    for cid, score in ranked:
        r = rows.get(cid)
        if not r:
            continue
        cos = 0.0
        if r["embedding"]:
            cos = float(np.frombuffer(r["embedding"], dtype="float32") @ qv)
        hits.append(Hit(cid, r["doc_id"], r["filename"], r["file_type"], r["page"], r["label"],
                        r["text"], score, coverage(query, r["text"]), cos))
    return hits


def search(vault, query: str, mode: str = "hybrid", filters: Filters | None = None,
           limit: int = 20) -> list[Hit]:
    query = query.strip()
    if not query:
        return []
    pool = max(limit * 4, 40)
    if mode == "keyword":
        ranked = _keyword_ids(vault, query, filters, limit)
    elif mode == "semantic":
        ranked = _semantic_ids(vault, query, filters, limit)
    else:  # hybrid: reciprocal-rank fusion
        fused: dict[int, float] = {}
        for lst in (_keyword_ids(vault, query, filters, pool), _semantic_ids(vault, query, filters, pool)):
            for rank, (cid, _) in enumerate(lst):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (60 + rank)
        ranked = sorted(fused.items(), key=lambda x: -x[1])[:limit]
    return _build_hits(vault, query, ranked)
