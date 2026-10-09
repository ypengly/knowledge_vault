from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QTableWidgetSelectionRange, QVBoxLayout, QWidget)
from PySide6.QtGui import QColor

from .. import ingest
from ..extract import SUPPORTED
from . import workers
from .common import human_size, short_date

COLUMNS = ["Filename", "Type", "Size", "Pages", "Imported", "Status", "Collections"]
FILTER = "Supported files (" + " ".join(f"*{e}" for e in SUPPORTED) + ");;All files (*)"


class LibraryPage(QWidget):
    changed = Signal()
    openDoc = Signal(int, int, str)

    def __init__(self, vault):
        super().__init__()
        self.setObjectName("page"); self.setAcceptDrops(True)
        self.vault, self.pending = vault, 0
        root = QHBoxLayout(self); root.setContentsMargins(24, 20, 24, 20)

        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Collections</b>"))
        self.colls = QListWidget(); self.colls.setMaximumWidth(210)
        left.addWidget(self.colls, 1)
        for text, fn in (("New collection…", self.new_collection), ("Rename…", self.rename_collection),
                         ("Delete collection", self.delete_collection)):
            b = QPushButton(text); b.clicked.connect(fn); left.addWidget(b)
        root.addLayout(left)

        right = QVBoxLayout()
        h = QLabel("Library"); h.setObjectName("h1"); right.addWidget(h)
        bar = QHBoxLayout()
        for text, fn, primary in (("Import files…", self.import_files, True), ("Import folder…", self.import_folder, False),
                                  ("Add web page…", self.add_url, False), ("Add to collection…", self.assign, False),
                                  ("Reprocess", self.reprocess, False), ("Delete", self.delete, False)):
            b = QPushButton(text)
            if primary:
                b.setObjectName("primary")
            b.clicked.connect(fn); bar.addWidget(b)
        bar.addStretch(1); right.addLayout(bar)
        hint = QLabel("Drag and drop files or folders anywhere on this page. Files are copied into your private "
                      "vault folder; nothing is uploaded."); hint.setObjectName("muted"); right.addWidget(hint)

        self.table = QTableWidget(0, len(COLUMNS)); self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.menu)
        self.table.cellDoubleClicked.connect(lambda r, c: self.open_row(r))
        right.addWidget(self.table, 1)
        self.status = QLabel(); self.status.setObjectName("muted"); right.addWidget(self.status)
        root.addLayout(right, 1)

        self.colls.currentRowChanged.connect(lambda _: self.refresh_table())
        self.timer = QTimer(self); self.timer.setInterval(800); self.timer.timeout.connect(self.refresh_table)
        self.refresh()

    # ---------------------------------------------------------------- data
    def current_collection(self) -> int | None:
        it = self.colls.currentItem()
        return it.data(256) if it else None

    def refresh(self) -> None:
        keep = self.current_collection()
        self.colls.blockSignals(True); self.colls.clear()
        all_item = QListWidgetItem(f"All documents"); all_item.setData(256, None); self.colls.addItem(all_item)
        for c in self.vault.db.collections():
            it = QListWidgetItem(f"{c['name']}  ({c['n']})"); it.setData(256, c["id"]); self.colls.addItem(it)
            if c["id"] == keep:
                self.colls.setCurrentItem(it)
        if not self.colls.currentItem():
            self.colls.setCurrentRow(0)
        self.colls.blockSignals(False)
        self.refresh_table()

    def refresh_table(self) -> None:
        docs = self.vault.db.list_documents(self.current_collection())
        sel = self.selected_ids()
        self.table.setRowCount(len(docs))
        for r, d in enumerate(docs):
            vals = [d["filename"], d["file_type"].upper(), human_size(d["size"]), str(d["pages"] or "—"),
                    short_date(d["imported_at"]), d["status"], d["collections"] or ""]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setData(256, d["id"])
                if c == 5:
                    if d["status"] == "failed":
                        it.setForeground(QColor('#c62828')); it.setToolTip(d["error"])
                    elif d["status"] != "ready":
                        it.setForeground(QColor('#b8860b'))
                    elif d["error"]:
                        it.setToolTip(d["error"])
                self.table.setItem(r, c, it)
            if d["id"] in sel:
                self.table.setRangeSelected(QTableWidgetSelectionRange(r, 0, r, len(COLUMNS) - 1), True)
        busy = sum(1 for d in docs if d["status"] in ("queued", "extracting", "indexing"))
        self.status.setText(f"{len(docs)} document(s)" + (f" · processing {busy}…" if busy else ""))
        if busy or self.pending:
            self.timer.start()
        else:
            self.timer.stop()

    def selected_ids(self) -> list[int]:
        rows = {i.row() for i in self.table.selectedIndexes()}
        return [self.table.item(r, 0).data(256) for r in sorted(rows) if self.table.item(r, 0)]

    # ---------------------------------------------------------------- import
    def enqueue(self, fn) -> None:
        self.pending += 1
        self.timer.start()

        def done(_=None):
            self.pending -= 1
            self.refresh(); self.changed.emit()

        def failed(e):
            QMessageBox.warning(self, "Import failed", str(e)); done()
        workers.run_async(fn, done, failed, workers.ingest_pool)

    def import_paths(self, paths: list[Path]) -> None:
        cids = [self.current_collection()] if self.current_collection() else []
        files: list[Path] = []
        for p in paths:
            files += [f for f in sorted(p.rglob("*")) if f.is_file()] if p.is_dir() else [p]
        skipped = [f.name for f in files if f.suffix.lower() not in SUPPORTED]
        for f in files:
            if f.suffix.lower() in SUPPORTED:
                self.enqueue(lambda f=f: ingest.import_file(self.vault, f, cids))
        if skipped:
            QMessageBox.information(self, "Skipped unsupported files",
                                    f"{len(skipped)} file(s) skipped:\n" + "\n".join(skipped[:15]))
        QTimer.singleShot(300, self.refresh_table)

    def import_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, "Import files", "", FILTER)
        self.import_paths([Path(n) for n in names])

    def import_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Import folder")
        if d:
            self.import_paths([Path(d)])

    def add_url(self) -> None:
        url, ok = QInputDialog.getText(self, "Add web page", "Page URL (http/https):")
        if not (ok and url.strip()):
            return
        if QMessageBox.question(self, "Download page?", f"Knowledge Vault will download this one page from the "
                                f"internet:\n\n{url.strip()}\n\nContinue?") != QMessageBox.StandardButton.Yes:
            return
        cids = [self.current_collection()] if self.current_collection() else []
        self.enqueue(lambda: ingest.import_url(self.vault, url.strip(), cids))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.import_paths([Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()])

    # ---------------------------------------------------------------- actions
    def open_row(self, row: int) -> None:
        self.openDoc.emit(self.table.item(row, 0).data(256), 1, "")

    def menu(self, pos) -> None:
        m = QMenu(self)
        m.addAction("Open", lambda: self.table.currentRow() >= 0 and self.open_row(self.table.currentRow()))
        m.addAction("Add to collection…", self.assign)
        if self.current_collection():
            m.addAction("Remove from this collection", self.unassign)
        m.addAction("Reprocess", self.reprocess); m.addAction("Delete", self.delete)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def assign(self) -> None:
        ids = self.selected_ids()
        colls = self.vault.db.collections()
        if not ids or not colls:
            return
        name, ok = QInputDialog.getItem(self, "Add to collection", "Collection:", [c["name"] for c in colls], 0, False)
        if ok:
            cid = next(c["id"] for c in colls if c["name"] == name)
            for i in ids:
                self.vault.db.assign(i, cid)
            self.refresh(); self.changed.emit()

    def unassign(self) -> None:
        for i in self.selected_ids():
            self.vault.db.unassign(i, self.current_collection())
        self.refresh(); self.changed.emit()

    def reprocess(self) -> None:
        for i in self.selected_ids():
            self.enqueue(lambda i=i: ingest.reprocess(self.vault, i))

    def delete(self) -> None:
        ids = self.selected_ids()
        if ids and QMessageBox.question(self, "Delete", f"Delete {len(ids)} document(s) from the vault?\n"
                                        "Your original files are not touched.") == QMessageBox.StandardButton.Yes:
            for i in ids:
                self.vault.delete_document(i)
            self.refresh(); self.changed.emit()

    def new_collection(self) -> None:
        name, ok = QInputDialog.getText(self, "New collection", "Name:")
        if ok and name.strip():
            try:
                self.vault.db.add_collection(name)
            except Exception as e:
                QMessageBox.warning(self, "Could not create", str(e))
            self.refresh(); self.changed.emit()

    def rename_collection(self) -> None:
        cid = self.current_collection()
        name, ok = QInputDialog.getText(self, "Rename collection", "New name:")
        if cid and ok and name.strip():
            self.vault.db.rename_collection(cid, name)
            self.refresh(); self.changed.emit()

    def delete_collection(self) -> None:
        cid = self.current_collection()
        if cid and QMessageBox.question(self, "Delete collection", "Delete this collection? Documents stay in the "
                                        "vault.") == QMessageBox.StandardButton.Yes:
            self.vault.db.delete_collection(cid)
            self.refresh(); self.changed.emit()
