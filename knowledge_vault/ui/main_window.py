from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QMainWindow, QStackedWidget, QWidget)

from .. import __version__
from .chat_page import ChatPage
from .common import PRIVACY_EXTERNAL, PRIVACY_LOCAL, STYLE
from .dashboard import DashboardPage
from .library import LibraryPage
from .notes_page import NotesPage
from .search_page import SearchPage
from .settings_page import SettingsPage
from .viewer import DocumentViewer


class MainWindow(QMainWindow):
    def __init__(self, vault):
        super().__init__()
        self.vault = vault
        self.setWindowTitle(f"Knowledge Vault {__version__}"); self.resize(1280, 820)
        self.setStyleSheet(STYLE)

        self.dashboard, self.library = DashboardPage(vault), LibraryPage(vault)
        self.search, self.chat = SearchPage(vault), ChatPage(vault)
        self.notes, self.settings = NotesPage(vault), SettingsPage(vault)
        self.pages = [("🏠  Dashboard", self.dashboard), ("📚  Library", self.library), ("🔎  Search", self.search),
                      ("💬  Ask", self.chat), ("📝  Notes", self.notes), ("⚙  Settings", self.settings)]

        self.nav = QListWidget(); self.nav.setObjectName("nav"); self.nav.setFixedWidth(190)
        self.stack = QStackedWidget()
        for title, page in self.pages:
            self.nav.addItem(title); self.stack.addWidget(page)
        central = QWidget(); lay = QHBoxLayout(central); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        lay.addWidget(self.nav); lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.privacy = QLabel(); self.statusBar().addPermanentWidget(self.privacy)

        self.nav.currentRowChanged.connect(self._on_nav)
        for i in range(len(self.pages)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda i=i: self.nav.setCurrentRow(i))

        for p in (self.library, self.search, self.chat, self.notes):
            p.openDoc.connect(self.open_document)
        self.library.changed.connect(self.refresh_all); self.notes.changed.connect(self.refresh_all)
        self.settings.changed.connect(self.refresh_all); self.chat.answered.connect(self.dashboard.refresh)
        self.dashboard.runSearch.connect(lambda q: (self.nav.setCurrentRow(2), self.search.run(q)))
        self.dashboard.askQuestion.connect(lambda q: (self.nav.setCurrentRow(3), self.chat.ask_text(q)))
        self.nav.setCurrentRow(0); self.refresh_all()

    def _on_nav(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        if row == 0:
            self.dashboard.refresh()
        elif row == 3:
            self.chat.refresh()

    def refresh_all(self) -> None:
        self.dashboard.refresh(); self.search.reload_collections(); self.chat.refresh(); self.notes.refresh()
        text, ext = self.vault.privacy_status()
        self.privacy.setText(("🌐 " if ext else "🔒 ") + text.split(" — ")[0].split(". ")[0])
        self.privacy.setStyleSheet(PRIVACY_EXTERNAL if ext else PRIVACY_LOCAL)
        self.privacy.setToolTip(text)

    def open_document(self, doc_id: int, page: int, query: str) -> None:
        if not self.vault.db.get_document(doc_id):
            return
        DocumentViewer(self.vault, doc_id, page, query, self).exec()
