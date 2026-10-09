from __future__ import annotations

import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from .. import qa
from ..llm import LLMError
from ..search import Filters
from . import workers
from .common import PRIVACY_EXTERNAL, PRIVACY_LOCAL, doc_link, esc, parse_doc_link


class ChatPage(QWidget):
    openDoc = Signal(int, int, str)
    answered = Signal()

    def __init__(self, vault):
        super().__init__()
        self.setObjectName("page"); self.vault = vault; self.html = ""; self.busy = False
        lay = QVBoxLayout(self); lay.setContentsMargins(24, 20, 24, 20)
        top = QHBoxLayout()
        h = QLabel("Ask your knowledge base"); h.setObjectName("h1")
        self.scope = QComboBox()
        top.addWidget(h, 1); top.addWidget(QLabel("Search in:")); top.addWidget(self.scope)
        lay.addLayout(top)
        self.privacy = QLabel(); self.privacy.setWordWrap(True); lay.addWidget(self.privacy)

        self.view = QTextBrowser(); self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        self.input = QLineEdit(); self.input.setPlaceholderText("e.g. What did my research say about customer retention?")
        self.send = QPushButton("Ask"); self.send.setObjectName("primary")
        clear = QPushButton("Clear")
        row.addWidget(self.input, 1); row.addWidget(self.send); row.addWidget(clear)
        lay.addLayout(row)
        self.send.clicked.connect(self.submit); self.input.returnPressed.connect(self.submit)
        clear.clicked.connect(self.clear)
        self.clear()

    def refresh(self) -> None:
        cur = self.scope.currentData()
        self.scope.clear(); self.scope.addItem("All collections", None)
        for c in self.vault.db.collections():
            self.scope.addItem(c["name"], c["id"])
        self.scope.setCurrentIndex(max(self.scope.findData(cur), 0))
        text, ext = self.vault.privacy_status()
        self.privacy.setText("🔒 " + text); self.privacy.setStyleSheet(PRIVACY_EXTERNAL if ext else PRIVACY_LOCAL)

    def clear(self) -> None:
        self.html = ("<p style='color:#6b7280'>Ask a question. Answers are built only from your own documents and "
                     "every answer lists the exact sources. If your documents don't contain the answer, you'll be "
                     "told so.</p>")
        self.view.setHtml(self.html); self.refresh()

    def ask_text(self, q: str) -> None:
        self.input.setText(q); self.submit()

    # ------------------------------------------------------------ flow
    def _append(self, fragment: str) -> None:
        self.html += fragment
        self.view.setHtml("<style>mark{background:#ffe066} a{color:#3b4bd8}</style>" + self.html)
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def _set_busy(self, on: bool) -> None:
        self.busy = on; self.send.setEnabled(not on); self.input.setEnabled(not on)

    def submit(self) -> None:
        q = self.input.text().strip()
        if not q or self.busy:
            return
        self.input.clear()
        self._append(f"<p style='background:#e8ebff;padding:8px;border-radius:6px'><b>You:</b> {esc(q)}</p>")
        try:
            provider = self.vault.provider()
        except LLMError as e:
            self._append(f"<p style='color:#b00020'>{esc(str(e))}</p>"); return
        flt = Filters(collection_id=self.scope.currentData())
        self._set_busy(True)
        if provider and provider.is_external and self.vault.settings.confirm_external:
            workers.run_async(lambda: qa.retrieve(self.vault, q, flt),
                              lambda hits: self._confirm_then_ask(q, flt, provider, hits), self._fail)
        else:
            self._run(q, flt, provider, allow=False)

    def _confirm_then_ask(self, q, flt, provider, hits) -> None:
        if hits:
            names = "\n".join(sorted({f"• {h.filename} ({h.label})" for h in hits}))
            box = QMessageBox.question(
                self, "Send passages to an external AI service?",
                f"To answer this, {len(hits)} passage(s) from your documents will be sent to:\n\n"
                f"{provider.label()}\n\nPassages come from:\n{names}\n\nSend them?")
            if box != QMessageBox.StandardButton.Yes:
                self._append("<p style='color:#8a5a00'>Cancelled — nothing was sent.</p>")
                self._set_busy(False); return
        self._run(q, flt, provider, allow=True)

    def _run(self, q, flt, provider, allow: bool) -> None:
        workers.run_async(lambda: qa.ask(self.vault, q, provider, flt, allow_external=allow),
                          lambda ans: self._render(q, ans), self._fail)

    def _fail(self, e) -> None:
        self._append(f"<p style='color:#b00020'><b>Error:</b> {esc(str(e))}</p>")
        self._set_busy(False)

    def _render(self, q: str, ans) -> None:
        self._set_busy(False)
        if not ans.grounded:
            self._append(f"<p style='background:#fff3d6;padding:8px;border-radius:6px'>{esc(ans.text)}</p>")
        else:
            body = esc(ans.text).replace("\n", "<br>")
            by_n = {c.n: c for c in ans.citations}
            body = re.sub(r"\[(\d+)\]", lambda m: (
                f"<a href='{doc_link(by_n[int(m.group(1))].doc_id, by_n[int(m.group(1))].page, q)}'>[{m.group(1)}]</a>"
                if int(m.group(1)) in by_n else m.group(0)), body)
            frag = f"<p><b>Answer:</b><br>{body}</p>"
            if ans.note:
                frag += f"<p style='color:#8a5a00'>⚠ {esc(ans.note)}</p>"
            frag += "<p><b>Sources</b></p>"
            for c in ans.citations:
                frag += (f"<div style='margin:4px 0 8px 0;padding-left:8px;border-left:3px solid #7c8cff'>"
                         f"[{c.n}] Source: <a href='{doc_link(c.doc_id, c.page, q)}'>{esc(c.filename)}</a><br>"
                         f"{esc(c.label)}<br><span style='color:#6b7280'>“{esc(c.snippet)}”</span></div>")
            self._append(frag)
        self._append(f"<p style='color:#9aa0b4;font-size:11px'>Processed by: {esc(ans.provider)}</p><hr>")
        self.answered.emit()

    def _link(self, url) -> None:
        p = parse_doc_link(url)
        if p:
            self.openDoc.emit(*p)
