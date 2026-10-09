from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QTabWidget, QTextBrowser, QVBoxLayout)

from ..textutil import highlight_html, tokens
from .common import esc


class DocumentViewer(QDialog):
    """Opens a document at an exact page/section with the query terms highlighted."""

    def __init__(self, vault, doc_id: int, page: int = 1, query: str = "", parent=None):
        super().__init__(parent)
        self.vault, self.doc_id, self.query = vault, doc_id, query
        doc = vault.db.get_document(doc_id)
        self.doc = doc
        self.setWindowTitle(doc["filename"] if doc else "Document")
        self.resize(900, 760)
        self.pages = vault.pages(doc_id)
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        title = QLabel(f"<b>{esc(doc['filename'])}</b>" if doc else "Document not found")
        self.combo = QComboBox()
        for p in self.pages:
            self.combo.addItem(p["label"], p["num"])
        prev, nxt = QPushButton("◀"), QPushButton("▶")
        openbtn = QPushButton("Open original file")
        top.addWidget(title, 1)
        top.addWidget(prev); top.addWidget(self.combo); top.addWidget(nxt); top.addWidget(openbtn)
        lay.addLayout(top)

        self.tabs = QTabWidget()
        self.page_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        scroll = QScrollArea(); scroll.setWidget(self.page_label); scroll.setWidgetResizable(True)
        self.text = QTextBrowser()
        self.tabs.addTab(scroll, "Page view")
        self.tabs.addTab(self.text, "Extracted text")
        lay.addWidget(self.tabs, 1)
        self.notes = QLabel(); self.notes.setObjectName("muted"); self.notes.setWordWrap(True)
        lay.addWidget(self.notes)

        self.combo.currentIndexChanged.connect(self._show)
        prev.clicked.connect(lambda: self.combo.setCurrentIndex(max(0, self.combo.currentIndex() - 1)))
        nxt.clicked.connect(lambda: self.combo.setCurrentIndex(min(self.combo.count() - 1, self.combo.currentIndex() + 1)))
        openbtn.clicked.connect(lambda: doc and QDesktopServices.openUrl(QUrl.fromLocalFile(doc["stored_path"])))

        idx = self.combo.findData(page)
        self.combo.setCurrentIndex(max(idx, 0))
        self._show()

    def _show(self) -> None:
        if not self.pages:
            return
        num = self.combo.currentData()
        row = next(p for p in self.pages if p["num"] == num)
        self.text.setHtml(f"<div style='line-height:150%'>{highlight_html(row['text'], self.query)}</div>")
        pix = self._render(num)
        self.tabs.setTabEnabled(0, pix is not None)
        if pix is not None:
            self.page_label.setPixmap(pix)
            self.tabs.setCurrentIndex(0)
        else:
            self.tabs.setCurrentIndex(1)
        linked = self.vault.db.notes_for_document(self.doc_id)
        self.notes.setText("Linked notes: " + ", ".join(esc(n["title"]) for n in linked) if linked else "")

    def _render(self, num: int) -> QPixmap | None:
        d = self.doc
        path = Path(d["stored_path"])
        if d["file_type"] == "image" and path.exists():
            return QPixmap(str(path)).scaledToWidth(820, Qt.TransformationMode.SmoothTransformation)
        if d["file_type"] != "pdf" or not path.exists():
            return None
        try:
            import fitz
            with fitz.open(str(path)) as pdf:
                page = pdf[num - 1]
                for term in dict.fromkeys(tokens(self.query)):
                    for rect in page.search_for(term):
                        page.add_highlight_annot(rect)  # in-memory only; the file is never modified
                pix = page.get_pixmap(dpi=130, alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            return QPixmap.fromImage(img)
        except Exception:
            return None
