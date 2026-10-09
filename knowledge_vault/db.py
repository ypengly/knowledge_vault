"""SQLite storage: documents, pages, chunks (+FTS5), collections, notes, history."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_COLLECTIONS = ["Work", "School", "Research", "Business", "Personal"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY, filename TEXT NOT NULL, stored_path TEXT, source TEXT,
  file_type TEXT NOT NULL, size INTEGER DEFAULT 0, pages INTEGER DEFAULT 0,
  imported_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
  error TEXT DEFAULT '', sha256 TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS pages(
  doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  num INTEGER NOT NULL, label TEXT NOT NULL, text TEXT NOT NULL,
  PRIMARY KEY(doc_id, num));
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY, doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL, page INTEGER NOT NULL, label TEXT NOT NULL,
  text TEXT NOT NULL, embedding BLOB);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, content='chunks', content_rowid='id', tokenize='porter unicode61');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES('delete', old.id, old.text); END;
CREATE TABLE IF NOT EXISTS collections(
  id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, builtin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS doc_collections(
  doc_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
  coll_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
  PRIMARY KEY(doc_id, coll_id));
CREATE TABLE IF NOT EXISTS notes(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
  folder TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS note_tags(
  note_id INTEGER REFERENCES notes(id) ON DELETE CASCADE, tag TEXT NOT NULL,
  PRIMARY KEY(note_id, tag));
CREATE TABLE IF NOT EXISTS note_docs(
  note_id INTEGER REFERENCES notes(id) ON DELETE CASCADE,
  doc_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
  PRIMARY KEY(note_id, doc_id));
CREATE TABLE IF NOT EXISTS searches(
  id INTEGER PRIMARY KEY, query TEXT NOT NULL, mode TEXT, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS questions(
  id INTEGER PRIMARY KEY, question TEXT NOT NULL, answer TEXT NOT NULL,
  citations TEXT NOT NULL DEFAULT '[]', grounded INTEGER DEFAULT 0,
  provider TEXT DEFAULT '', at TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """One connection per thread (workers run off the UI thread)."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        self._local = threading.local()
        with self.conn:
            self.conn.executescript(SCHEMA)
            for name in DEFAULT_COLLECTIONS:
                self.conn.execute(
                    "INSERT OR IGNORE INTO collections(name, builtin) VALUES(?,1)", (name,))

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA journal_mode=WAL")
            self._local.c = c
        return c

    # -- generic helpers
    def q(self, sql: str, args=()):
        return self.conn.execute(sql, args).fetchall()

    def one(self, sql: str, args=()):
        return self.conn.execute(sql, args).fetchone()

    def run(self, sql: str, args=()) -> int:
        with self.conn:
            return self.conn.execute(sql, args).lastrowid

    def get_meta(self, key: str, default: str = "") -> str:
        r = self.one("SELECT value FROM meta WHERE key=?", (key,))
        return r["value"] if r else default

    def set_meta(self, key: str, value: str) -> None:
        self.run("INSERT INTO meta(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # -- documents
    def list_documents(self, collection_id: int | None = None):
        sql = ("SELECT d.*, (SELECT group_concat(c.name, ', ') FROM doc_collections dc "
               "JOIN collections c ON c.id=dc.coll_id WHERE dc.doc_id=d.id) AS collections "
               "FROM documents d")
        args: tuple = ()
        if collection_id:
            sql += " WHERE d.id IN (SELECT doc_id FROM doc_collections WHERE coll_id=?)"
            args = (collection_id,)
        return self.q(sql + " ORDER BY d.imported_at DESC, d.id DESC", args)

    def get_document(self, doc_id: int):
        return self.one("SELECT * FROM documents WHERE id=?", (doc_id,))

    def delete_document(self, doc_id: int) -> str | None:
        d = self.get_document(doc_id)
        self.run("DELETE FROM documents WHERE id=?", (doc_id,))
        return d["stored_path"] if d else None

    def set_status(self, doc_id: int, status: str, error: str = "") -> None:
        self.run("UPDATE documents SET status=?, error=? WHERE id=?", (status, error, doc_id))

    # -- collections
    def collections(self):
        return self.q("SELECT c.*, (SELECT COUNT(*) FROM doc_collections WHERE coll_id=c.id) AS n "
                      "FROM collections c ORDER BY builtin DESC, name COLLATE NOCASE")

    def add_collection(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Collection name is empty")
        return self.run("INSERT INTO collections(name) VALUES(?)", (name,))

    def rename_collection(self, cid: int, name: str) -> None:
        self.run("UPDATE collections SET name=? WHERE id=? AND builtin=0", (name.strip(), cid))

    def delete_collection(self, cid: int) -> None:
        self.run("DELETE FROM collections WHERE id=? AND builtin=0", (cid,))

    def assign(self, doc_id: int, cid: int) -> None:
        self.run("INSERT OR IGNORE INTO doc_collections VALUES(?,?)", (doc_id, cid))

    def unassign(self, doc_id: int, cid: int) -> None:
        self.run("DELETE FROM doc_collections WHERE doc_id=? AND coll_id=?", (doc_id, cid))

    # -- notes
    def save_note(self, note_id, title, body, folder, tags, doc_ids) -> int:
        t = now()
        with self.conn:
            if note_id:
                self.conn.execute("UPDATE notes SET title=?, body=?, folder=?, updated=? WHERE id=?",
                                  (title, body, folder, t, note_id))
            else:
                note_id = self.conn.execute(
                    "INSERT INTO notes(title,body,folder,created,updated) VALUES(?,?,?,?,?)",
                    (title, body, folder, t, t)).lastrowid
            self.conn.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
            for tag in sorted({x.strip().lower().lstrip('#') for x in tags if x.strip()}):
                self.conn.execute("INSERT INTO note_tags VALUES(?,?)", (note_id, tag))
            self.conn.execute("DELETE FROM note_docs WHERE note_id=?", (note_id,))
            for d in set(doc_ids):
                self.conn.execute("INSERT INTO note_docs VALUES(?,?)", (note_id, d))
        return note_id

    def get_note(self, note_id: int):
        n = self.one("SELECT * FROM notes WHERE id=?", (note_id,))
        if not n:
            return None
        tags = [r["tag"] for r in self.q("SELECT tag FROM note_tags WHERE note_id=? ORDER BY tag", (note_id,))]
        docs = [r["doc_id"] for r in self.q("SELECT doc_id FROM note_docs WHERE note_id=?", (note_id,))]
        return {**dict(n), "tags": tags, "doc_ids": docs}

    def delete_note(self, note_id: int) -> None:
        self.run("DELETE FROM notes WHERE id=?", (note_id,))

    def list_notes(self, text: str = "", folder: str = "", tag: str = ""):
        sql, args = "SELECT n.* FROM notes n WHERE 1=1", []
        if text:
            sql += " AND (n.title LIKE ? OR n.body LIKE ?)"
            args += [f"%{text}%"] * 2
        if folder:
            sql += " AND n.folder=?"
            args.append(folder)
        if tag:
            sql += " AND n.id IN (SELECT note_id FROM note_tags WHERE tag=?)"
            args.append(tag.lower().lstrip('#'))
        return self.q(sql + " ORDER BY n.updated DESC", tuple(args))

    def note_folders(self):
        return [r["folder"] for r in self.q("SELECT DISTINCT folder FROM notes WHERE folder<>'' ORDER BY folder")]

    def note_tags(self):
        return [r["tag"] for r in self.q("SELECT DISTINCT tag FROM note_tags ORDER BY tag")]

    def notes_for_document(self, doc_id: int):
        return self.q("SELECT n.id, n.title FROM notes n JOIN note_docs nd ON nd.note_id=n.id "
                      "WHERE nd.doc_id=?", (doc_id,))

    # -- history
    def log_search(self, query: str, mode: str) -> None:
        self.run("INSERT INTO searches(query,mode,at) VALUES(?,?,?)", (query, mode, now()))

    def log_question(self, question, answer, citations_json, grounded, provider) -> None:
        self.run("INSERT INTO questions(question,answer,citations,grounded,provider,at) "
                 "VALUES(?,?,?,?,?,?)", (question, answer, citations_json, int(grounded), provider, now()))

    def recent_searches(self, n=8):
        return self.q("SELECT query, mode, at FROM searches ORDER BY id DESC LIMIT ?", (n,))

    def recent_questions(self, n=8):
        return self.q("SELECT question, grounded, at FROM questions ORDER BY id DESC LIMIT ?", (n,))

    # -- stats
    def stats(self, files_dir: Path) -> dict:
        size = sum(f.stat().st_size for f in files_dir.glob("*") if f.is_file()) if files_dir.exists() else 0
        try:
            size += Path(self.path).stat().st_size
        except OSError:
            pass
        return {
            "documents": self.one("SELECT COUNT(*) c FROM documents")["c"],
            "ready": self.one("SELECT COUNT(*) c FROM documents WHERE status='ready'")["c"],
            "chunks": self.one("SELECT COUNT(*) c FROM chunks")["c"],
            "collections": self.one("SELECT COUNT(*) c FROM collections")["c"],
            "notes": self.one("SELECT COUNT(*) c FROM notes")["c"],
            "storage_bytes": size,
        }
