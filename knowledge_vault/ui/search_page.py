from __future__ import annotations

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..search import Filters
from ..textutil import best_snippet, highlight_html
from . import workers
from .common import doc_link, esc, parse_doc_link

TYPES = [("All file types", None), ("PDF", ["pdf"]), ("Word (DOCX)", ["docx"]), ("Text", ["txt"]),
         ("Markdown", ["md"]), ("CSV", ["csv"]), ("Images (OCR)", ["image"]), ("Web pages", ["url"])]


class SearchPage(QWidget):
    openDoc = Signal(int, int, str)

    def __init__(self, vault):
        super().__init__()
        self.setObjectName("page"); self.vault = vault
        lay = QVBoxLayout(self); lay.setContentsMargins(24, 20, 24, 20)
        h = QLabel("Search"); h.setObjectName("h1"); lay.addWidget(h)

        row = QHBoxLayout()
        self.query = QLineEdit(); self.query.setPlaceholderText("Search your knowledge base…")
        self.mode = QComboBox()
        for label, key in (("Hybrid (keyword + semantic)", "hybrid"), ("Keyword", "keyword"), ("Semantic", "semantic")):
            self.mode.addItem(label, key)
        go = QPushButton("Search"); go.setObjectName("primary")
        row.addWidget(self.query, 1); row.addWidget(self.mode); row.addWidget(go)
        lay.addLayout(row)

        f = QHBoxLayout()
        self.coll, self.ftype = QComboBox(), QComboBox()
        for label, key in TYPES:
            self.ftype.addItem(label, key)
        self.use_date = QCheckBox("Imported between")
        self.d_from, self.d_to = QDateEdit(QDate.currentDate().addMonths(-1)), QDateEdit(QDate.currentDate())
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True); d.setDisplayFormat("yyyy-MM-dd"); d.setEnabled(False)
        self.use_date.toggled.connect(lambda on: [d.setEnabled(on) for d in (self.d_from, self.d_to)])
        for w in (QLabel("Collection:"), self.coll, QLabel("Type:"), self.ftype, self.use_date, self.d_from,
                  QLabel("and"), self.d_to):
            f.addWidget(w)
        f.addStretch(1); lay.addLayout(f)

        self.info = QLabel(); self.info.setObjectName("muted"); lay.addWidget(self.info)
        self.out = QTextBrowser(); self.out.setOpenLinks(False)
        self.out.anchorClicked.connect(self._link)
        lay.addWidget(self.out, 1)
        go.clicked.connect(self.run); self.query.returnPressed.connect(self.run)
        self.reload_collections()

    def reload_collections(self) -> None:
        cur = self.coll.currentData()
        self.coll.clear(); self.coll.addItem("All collections", None)
        for c in self.vault.db.collections():
            self.coll.addItem(c["name"], c["id"])
        i = self.coll.findData(cur)
        self.coll.setCurrentIndex(max(i, 0))

    def filters(self) -> Filters:
        return Filters(self.coll.currentData(), self.ftype.currentData(),
                       self.d_from.date().toString("yyyy-MM-dd") if self.use_date.isChecked() else None,
                       self.d_to.date().toString("yyyy-MM-dd") if self.use_date.isChecked() else None)

    def run(self, text: str | None = None) -> None:
        if isinstance(text, str):
            self.query.setText(text)
        q, mode, flt = self.query.text().strip(), self.mode.currentData(), self.filters()
        if not q:
            return
        self.info.setText("Searching…")
        workers.run_async(lambda: self.vault.search(q, mode, flt, 25),
                          lambda hits: self._show(q, hits), lambda e: self.info.setText(f"Search failed: {e}"))

    def _show(self, q: str, hits) -> None:
        if not hits:
            self.info.setText("No matching passages. Try fewer words, another mode, or clear the filters.")
            self.out.setHtml(""); return
        self.info.setText(f"{len(hits)} matching passage(s) — click a result to open it at that page.")
        parts = []
        for h in hits:
            snippet = highlight_html(best_snippet(h.text, q), q)
            parts.append(
                f"<p><a href='{doc_link(h.doc_id, h.page, q)}'><b>{esc(h.filename)}</b></a> "
                f"<span style='color:#6b7280'>· {esc(h.label)} · {h.file_type.upper()}</span><br>{snippet}</p><hr>")
        self.out.setHtml("<style>mark{background:#ffe066}</style>" + "".join(parts))

    def _link(self, url) -> None:
        p = parse_doc_link(url)
        if p:
            self.openDoc.emit(*p)
