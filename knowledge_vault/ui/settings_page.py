from __future__ import annotations

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QProgressDialog,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

from .. import keystore
from ..embeddings import make_embedder
from ..llm import PROVIDERS, LLMError, make_provider
from . import workers


class SettingsPage(QWidget):
    changed = Signal()

    def __init__(self, vault):
        super().__init__()
        self.setObjectName("page"); self.vault = vault
        lay = QVBoxLayout(self); lay.setContentsMargins(24, 20, 24, 20)
        h = QLabel("Settings & privacy"); h.setObjectName("h1"); lay.addWidget(h)
        info = QLabel("Knowledge Vault is local-first. Importing, extraction, OCR, indexing and search always run on "
                      "this computer. Text is sent to an AI service only if you pick an external provider below "
                      "<b>and</b> confirm a question. API keys are never saved in files by this app.")
        info.setWordWrap(True); lay.addWidget(info)
        form = QFormLayout(); lay.addLayout(form)
        s = vault.settings

        self.provider = QComboBox()
        for k, v in PROVIDERS.items():
            self.provider.addItem(v, k)
        self.provider.setCurrentIndex(max(self.provider.findData(s.llm_provider), 0))
        self.model = QLineEdit(s.llm_model); self.model.setPlaceholderText("model name, e.g. llama3.1 (Ollama)")
        self.base = QLineEdit(s.llm_base_url); self.base.setPlaceholderText("blank = provider default")
        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("API key (kept in memory for this session)")
        self.remember = QCheckBox("Remember key in the Windows Credential Manager / OS keyring")
        self.remember.setEnabled(keystore.keyring_available())
        if not keystore.keyring_available():
            self.remember.setToolTip("Install the optional 'keyring' package to enable this.")
        self.confirm = QCheckBox("Ask me before every request to an external AI service (recommended)")
        self.confirm.setChecked(s.confirm_external)
        self.embedder = QComboBox()
        self.embedder.addItem("Built-in lexical index (fast, no downloads)", "hashing")
        self.embedder.addItem("Local neural embeddings (needs sentence-transformers)", "sentence_transformers")
        self.embedder.setCurrentIndex(max(self.embedder.findData(s.embedder), 0))
        self.st_model = QLineEdit(s.st_model)
        self.chunk, self.overlap, self.topk = QSpinBox(), QSpinBox(), QSpinBox()
        self.chunk.setRange(40, 800); self.chunk.setValue(s.chunk_words)
        self.overlap.setRange(0, 200); self.overlap.setValue(s.chunk_overlap)
        self.topk.setRange(1, 20); self.topk.setValue(s.top_k)
        self.ocr_lang = QLineEdit(s.ocr_lang); self.tess = QLineEdit(s.tesseract_cmd)
        self.tess.setPlaceholderText(r"C:\Program Files\Tesseract-OCR\tesseract.exe (blank = PATH)")

        for label, w in (("AI answer provider", self.provider), ("Model", self.model), ("Base URL", self.base),
                         ("API key", self.key), ("", self.remember), ("", self.confirm),
                         ("Embedding model", self.embedder), ("Neural model name", self.st_model),
                         ("Chunk size (words)", self.chunk), ("Chunk overlap (words)", self.overlap),
                         ("Passages per answer", self.topk), ("OCR language", self.ocr_lang),
                         ("Tesseract path", self.tess)):
            form.addRow(label, w)

        save = QPushButton("Save settings"); save.setObjectName("primary")
        test = QPushButton("Test AI connection"); folder = QPushButton("Open data folder")
        for b in (save, test, folder):
            lay.addWidget(b)
        lay.addStretch(1)
        save.clicked.connect(self.save); test.clicked.connect(self.test); folder.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(vault.dir))))

    def save(self) -> None:
        s = self.vault.settings
        old_embedder = (s.embedder, s.st_model)
        s.llm_provider, s.llm_model = self.provider.currentData(), self.model.text().strip()
        s.llm_base_url = self.base.text().strip(); s.confirm_external = self.confirm.isChecked()
        s.embedder, s.st_model = self.embedder.currentData(), self.st_model.text().strip() or "all-MiniLM-L6-v2"
        s.chunk_words, s.chunk_overlap, s.top_k = self.chunk.value(), self.overlap.value(), self.topk.value()
        s.ocr_lang, s.tesseract_cmd = self.ocr_lang.text().strip() or "eng", self.tess.text().strip()
        key = self.key.text().strip()
        if key and s.llm_provider != "none":
            keystore.set_session_key(s.llm_provider, key)
            if self.remember.isChecked() and not keystore.store_in_keyring(s.llm_provider, key):
                QMessageBox.warning(self, "Keyring", "Could not store the key in the OS keyring.")
            self.key.clear()
        s.save(self.vault.dir)
        if (s.embedder, s.st_model) != old_embedder:
            self._switch_embedder()
        else:
            self.changed.emit()

    def _switch_embedder(self) -> None:
        s = self.vault.settings
        dlg = QProgressDialog("Re-indexing your documents with the new embedding model…", None, 0, 0, self)
        dlg.setWindowTitle("Re-indexing"); dlg.setMinimumDuration(0); dlg.show()

        def job():
            self.vault.set_embedder(make_embedder(s.embedder, s.st_model))
            self.vault.reindex()

        def done(_):
            dlg.close(); self.changed.emit()

        def fail(e):
            dlg.close()
            QMessageBox.warning(self, "Embedding model", f"{e}\n\nFalling back to the built-in index.")
            s.embedder = "hashing"; s.save(self.vault.dir)
            self.embedder.setCurrentIndex(0)
            workers.run_async(lambda: (self.vault.set_embedder(make_embedder("hashing")), self.vault.reindex()),
                              lambda _: self.changed.emit())
        workers.run_async(job, done, fail)

    def test(self) -> None:
        self.save()
        try:
            p = make_provider(self.vault.settings)
        except LLMError as e:
            QMessageBox.warning(self, "AI connection", str(e)); return
        if p is None:
            QMessageBox.information(self, "AI connection", "No AI provider selected — answers will show matching "
                                    "passages only."); return
        if p.is_external and QMessageBox.question(
                self, "Send test message?", f"Send a short test message (no document content) to:\n{p.label()}?"
        ) != QMessageBox.StandardButton.Yes:
            return
        workers.run_async(lambda: p.generate("Reply with the single word OK.", "ping"),
                          lambda r: QMessageBox.information(self, "AI connection", f"Connected. Reply: {r[:80]}"),
                          lambda e: QMessageBox.warning(self, "AI connection", str(e)))
