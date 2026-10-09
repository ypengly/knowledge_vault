from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout,
                               QWidget)


class NotesPage(QWidget):
    changed = Signal()
    openDoc = Signal(int, int, str)

    def __init__(self, vault):
        super().__init__()
        self.setObjectName("page"); self.vault = vault
        self.note_id: int | None = None; self.dirty = False; self.doc_ids: list[int] = []
        root = QHBoxLayout(self); root.setContentsMargins(24, 20, 24, 20)

        left = QVBoxLayout()
        h = QLabel("Notes"); h.setObjectName("h1"); left.addWidget(h)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search notes…")
        self.folder, self.tag = QComboBox(), QComboBox()
        self.lst = QListWidget(); self.lst.setMaximumWidth(280)
        new = QPushButton("New note"); new.setObjectName("primary")
        for w in (self.search, self.folder, self.tag, self.lst, new):
            left.addWidget(w)
        root.addLayout(left)

        right = QVBoxLayout()
        self.title = QLineEdit(); self.title.setPlaceholderText("Title")
        meta = QHBoxLayout()
        self.folder_edit = QLineEdit(); self.folder_edit.setPlaceholderText("Folder (e.g. Research/Ideas)")
        self.tags_edit = QLineEdit(); self.tags_edit.setPlaceholderText("Tags, comma separated")
        meta.addWidget(self.folder_edit); meta.addWidget(self.tags_edit)
        self.editor = QPlainTextEdit(); self.editor.setPlaceholderText("Write in Markdown…")
        self.preview = QTextBrowser(); self.preview.setVisible(False)
        bar = QHBoxLayout()
        self.save_btn = QPushButton("Save"); self.save_btn.setObjectName("primary")
        self.prev_btn = QPushButton("Preview"); self.prev_btn.setCheckable(True)
        del_btn = QPushButton("Delete")
        bar.addWidget(self.save_btn); bar.addWidget(self.prev_btn); bar.addStretch(1); bar.addWidget(del_btn)
        links = QHBoxLayout()
        self.links = QListWidget(); self.links.setMaximumHeight(90)
        lb = QVBoxLayout()
        link_btn, unlink_btn = QPushButton("Link document…"), QPushButton("Unlink")
        lb.addWidget(link_btn); lb.addWidget(unlink_btn); lb.addStretch(1)
        links.addWidget(QLabel("Linked documents:")); links.addWidget(self.links, 1); links.addLayout(lb)
        for item in (self.title,):
            right.addWidget(item)
        right.addLayout(meta); right.addWidget(self.editor, 1); right.addWidget(self.preview, 1)
        right.addLayout(bar); right.addLayout(links)
        root.addLayout(right, 1)

        self.search.textChanged.connect(self.reload_list)
        self.folder.currentIndexChanged.connect(self.reload_list); self.tag.currentIndexChanged.connect(self.reload_list)
        self.lst.itemClicked.connect(lambda it: self.load(it.data(256)))
        new.clicked.connect(self.new_note); self.save_btn.clicked.connect(self.save)
        self.prev_btn.toggled.connect(self.toggle_preview); del_btn.clicked.connect(self.delete)
        link_btn.clicked.connect(self.link_doc); unlink_btn.clicked.connect(self.unlink_doc)
        self.links.itemDoubleClicked.connect(lambda it: self.openDoc.emit(it.data(256), 1, ""))
        for w in (self.title, self.folder_edit, self.tags_edit):
            w.textEdited.connect(self._mark)
        self.editor.textChanged.connect(self._mark)
        self.new_note(); self.refresh()

    def _mark(self, *_):
        self.dirty = True

    def refresh(self) -> None:
        for combo, first, items in ((self.folder, "All folders", self.vault.db.note_folders()),
                                    (self.tag, "All tags", self.vault.db.note_tags())):
            cur = combo.currentData()
            combo.blockSignals(True); combo.clear(); combo.addItem(first, "")
            for i in items:
                combo.addItem(i, i)
            combo.setCurrentIndex(max(combo.findData(cur), 0)); combo.blockSignals(False)
        self.reload_list()

    def reload_list(self) -> None:
        self.lst.clear()
        for n in self.vault.db.list_notes(self.search.text().strip(), self.folder.currentData() or "",
                                          self.tag.currentData() or ""):
            it = QListWidgetItem(("📁 " + n["folder"] + " / " if n["folder"] else "") + n["title"])
            it.setData(256, n["id"]); self.lst.addItem(it)

    def new_note(self) -> None:
        if not self._maybe_save():
            return
        self.note_id, self.doc_ids = None, []
        for w in (self.title, self.folder_edit, self.tags_edit):
            w.clear()
        self.editor.clear(); self._show_links(); self.dirty = False

    def load(self, nid: int) -> None:
        if nid == self.note_id or not self._maybe_save():
            return
        n = self.vault.db.get_note(nid)
        if not n:
            return
        self.note_id, self.doc_ids = nid, n["doc_ids"]
        self.title.setText(n["title"]); self.folder_edit.setText(n["folder"])
        self.tags_edit.setText(", ".join(n["tags"])); self.editor.setPlainText(n["body"])
        self._show_links(); self.dirty = False
        if self.prev_btn.isChecked():
            self.toggle_preview(True)

    def _maybe_save(self) -> bool:
        if self.dirty and (self.title.text().strip() or self.editor.toPlainText().strip()):
            self.save()
        return True

    def save(self) -> None:
        title = self.title.text().strip() or (self.editor.toPlainText().strip().splitlines() or ["Untitled"])[0][:60]
        tags = [t for t in self.tags_edit.text().split(",")]
        self.note_id = self.vault.db.save_note(self.note_id, title, self.editor.toPlainText(),
                                               self.folder_edit.text().strip(), tags, self.doc_ids)
        self.title.setText(title); self.dirty = False
        self.refresh(); self.changed.emit()

    def delete(self) -> None:
        if self.note_id and QMessageBox.question(self, "Delete note", "Delete this note?") == QMessageBox.StandardButton.Yes:
            self.vault.db.delete_note(self.note_id)
            self.note_id = None; self.dirty = False; self.new_note(); self.refresh(); self.changed.emit()

    def toggle_preview(self, on: bool) -> None:
        self.preview.setVisible(on); self.editor.setVisible(not on)
        if on:
            self.preview.setMarkdown(self.editor.toPlainText())

    def _show_links(self) -> None:
        self.links.clear()
        for d in self.doc_ids:
            doc = self.vault.db.get_document(d)
            if doc:
                it = QListWidgetItem(doc["filename"]); it.setData(256, d); self.links.addItem(it)

    def link_doc(self) -> None:
        docs = [d for d in self.vault.db.list_documents() if d["id"] not in self.doc_ids]
        if not docs:
            QMessageBox.information(self, "Link document", "No more documents to link."); return
        name, ok = QInputDialog.getItem(self, "Link document", "Document:", [d["filename"] for d in docs], 0, False)
        if ok:
            self.doc_ids.append(next(d["id"] for d in docs if d["filename"] == name))
            self._show_links(); self.dirty = True

    def unlink_doc(self) -> None:
        it = self.links.currentItem()
        if it:
            self.doc_ids.remove(it.data(256)); self._show_links(); self.dirty = True
