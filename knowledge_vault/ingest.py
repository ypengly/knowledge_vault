"""Import pipeline: register -> extract -> chunk -> embed -> index."""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Callable

import numpy as np

from .chunker import chunk_text
from .db import now
from .extract import ExtractionError, extract, fetch_url, file_type_for

Notify = Callable[[int, str], None]


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def register_file(vault, path: Path, collection_ids: list[int] | None = None) -> tuple[int, bool]:
    """Copy the file into the vault and create a 'queued' row. Returns (doc_id, is_new)."""
    path = Path(path)
    ftype = file_type_for(path)
    if not ftype:
        raise ExtractionError(f"Unsupported file type: {path.suffix or path.name}")
    digest = _sha(path)
    dup = vault.db.one("SELECT id FROM documents WHERE sha256=?", (digest,))
    if dup:
        for cid in collection_ids or []:
            vault.db.assign(dup["id"], cid)
        return dup["id"], False
    stored = vault.files_dir / f"{digest[:12]}_{re.sub(r'[^\w.\-]+', '_', path.name)}"
    shutil.copy2(path, stored)
    doc_id = vault.db.run(
        "INSERT INTO documents(filename, stored_path, source, file_type, size, imported_at, status, sha256) "
        "VALUES(?,?,?,?,?,?, 'queued', ?)",
        (path.name, str(stored), str(path), ftype, path.stat().st_size, now(), digest))
    for cid in collection_ids or []:
        vault.db.assign(doc_id, cid)
    return doc_id, True


def process_document(vault, doc_id: int, notify: Notify | None = None) -> None:
    notify = notify or (lambda *_: None)
    db, s = vault.db, vault.settings
    d = db.get_document(doc_id)
    try:
        db.set_status(doc_id, "extracting"); notify(doc_id, "extracting")
        res = extract(Path(d["stored_path"]), d["file_type"], s.ocr_lang, s.tesseract_cmd)
        db.set_status(doc_id, "indexing"); notify(doc_id, "indexing")
        rows, texts = [], []
        for u in res.units:
            for i, c in enumerate(chunk_text(u.text, s.chunk_words, s.chunk_overlap)):
                rows.append((u.num, u.label, c)); texts.append(c)
        vecs = vault.embedder.embed(texts) if texts else np.zeros((0, vault.embedder.dim), "float32")
        with db.conn:
            db.conn.execute("DELETE FROM pages WHERE doc_id=?", (doc_id,))
            db.conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
            db.conn.executemany("INSERT INTO pages VALUES(?,?,?,?)",
                                [(doc_id, u.num, u.label, u.text) for u in res.units])
            ids = []
            for idx, ((page, label, text), v) in enumerate(zip(rows, vecs)):
                cur = db.conn.execute(
                    "INSERT INTO chunks(doc_id, idx, page, label, text, embedding) VALUES(?,?,?,?,?,?)",
                    (doc_id, idx, page, label, text, v.astype("float32").tobytes()))
                ids.append(cur.lastrowid)
            db.conn.execute("UPDATE documents SET pages=?, status='ready', error=? WHERE id=?",
                            (res.page_count, "; ".join(res.warnings), doc_id))
        if ids:
            vault.index.add(ids, vecs)
        notify(doc_id, "ready")
    except Exception as e:  # report every failure on the row, never crash the worker
        db.set_status(doc_id, "failed", str(e) or e.__class__.__name__)
        notify(doc_id, "failed")


def import_file(vault, path: Path, collection_ids=None, notify: Notify | None = None) -> int:
    doc_id, is_new = register_file(vault, path, collection_ids)
    if notify:
        notify(doc_id, "queued")
    if is_new:
        process_document(vault, doc_id, notify)
    return doc_id


def import_url(vault, url: str, collection_ids=None, notify: Notify | None = None) -> int:
    """Downloads exactly the URL the user typed (explicit action), stores it as text."""
    title, text = fetch_url(url)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    dup = vault.db.one("SELECT id FROM documents WHERE sha256=?", (digest,))
    if dup:
        return dup["id"]
    name = re.sub(r"[^\w.\-]+", "_", title)[:60] or "page"
    stored = vault.files_dir / f"{digest[:12]}_{name}.txt"
    stored.write_text(f"{title}\n{url}\n\n{text}", "utf-8")
    doc_id = vault.db.run(
        "INSERT INTO documents(filename, stored_path, source, file_type, size, imported_at, status, sha256) "
        "VALUES(?,?,?,?,?,?, 'queued', ?)",
        (title[:120], str(stored), url, "url", stored.stat().st_size, now(), digest))
    for cid in collection_ids or []:
        vault.db.assign(doc_id, cid)
    # the stored copy is plain text; extract it through the txt path
    vault.db.run("UPDATE documents SET file_type='url' WHERE id=?", (doc_id,))
    if notify:
        notify(doc_id, "queued")
    process_document(vault, doc_id, notify)
    return doc_id


def reprocess(vault, doc_id: int, notify: Notify | None = None) -> None:
    process_document(vault, doc_id, notify)
    vault.load_index()  # drop vectors of the replaced chunks
