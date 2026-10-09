from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QVBoxLayout, QWidget)

from .common import human_size, short_date


class DashboardPage(QWidget):
    runSearch = Signal(str)
    askQuestion = Signal(str)

    def __init__(self, vault):
        super().__init__()
        self.setObjectName("page")
        self.vault = vault
        lay = QVBoxLayout(self); lay.setContentsMargins(24, 20, 24, 20)
        h = QLabel("Dashboard"); h.setObjectName("h1"); lay.addWidget(h)
        self.privacy = QLabel(); self.privacy.setWordWrap(True); lay.addWidget(self.privacy)

        row = QHBoxLayout(); self.stats = {}
        for key, title in (("documents", "Documents"), ("collections", "Collections"),
                           ("notes", "Notes"), ("storage", "Storage used")):
            card = QFrame(); card.setObjectName("card")
            cl = QVBoxLayout(card)
            num = QLabel("0"); num.setObjectName("statNum")
            lbl = QLabel(title); lbl.setObjectName("muted")
            cl.addWidget(num); cl.addWidget(lbl)
            self.stats[key] = num; row.addWidget(card)
        lay.addLayout(row)
        self.detail = QLabel(); self.detail.setObjectName("muted"); lay.addWidget(self.detail)

        grid = QGridLayout()
        self.searches, self.questions = QListWidget(), QListWidget()
        grid.addWidget(QLabel("<b>Recent searches</b> (double-click to run)"), 0, 0)
        grid.addWidget(QLabel("<b>Recent questions</b> (double-click to ask again)"), 0, 1)
        grid.addWidget(self.searches, 1, 0); grid.addWidget(self.questions, 1, 1)
        lay.addLayout(grid, 1)
        self.searches.itemDoubleClicked.connect(lambda i: self.runSearch.emit(i.data(256)))
        self.questions.itemDoubleClicked.connect(lambda i: self.askQuestion.emit(i.data(256)))

    def refresh(self) -> None:
        s = self.vault.db.stats(self.vault.files_dir)
        self.stats["documents"].setText(str(s["documents"]))
        self.stats["collections"].setText(str(s["collections"]))
        self.stats["notes"].setText(str(s["notes"]))
        self.stats["storage"].setText(human_size(s["storage_bytes"]))
        self.detail.setText(f"{s['ready']} of {s['documents']} documents ready · {s['chunks']} passages indexed · "
                            f"vector index: {self.vault.index.backend} · data folder: {self.vault.dir}")
        text, ext = self.vault.privacy_status()
        from .common import PRIVACY_EXTERNAL, PRIVACY_LOCAL
        self.privacy.setText("🔒 " + text); self.privacy.setStyleSheet(PRIVACY_EXTERNAL if ext else PRIVACY_LOCAL)
        self.searches.clear(); self.questions.clear()
        from PySide6.QtWidgets import QListWidgetItem
        for r in self.vault.db.recent_searches():
            it = QListWidgetItem(f"{r['query']}   ·   {r['mode']}   ·   {short_date(r['at'])}")
            it.setData(256, r["query"]); self.searches.addItem(it)
        for r in self.vault.db.recent_questions():
            mark = "✓" if r["grounded"] else "✗ no answer"
            it = QListWidgetItem(f"{r['question']}   ·   {mark}   ·   {short_date(r['at'])}")
            it.setData(256, r["question"]); self.questions.addItem(it)
