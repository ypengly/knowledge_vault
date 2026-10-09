from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, quote, urlparse

from PySide6.QtCore import QUrl

STYLE = """
* { font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }
QMainWindow, QWidget#page { background: #f6f7fb; }
QListWidget#nav { background: #1f2437; color: #c9cfe6; border: none; padding-top: 12px; outline: 0; }
QListWidget#nav::item { padding: 12px 18px; border-left: 3px solid transparent; }
QListWidget#nav::item:selected { background: #2b3250; color: white; border-left: 3px solid #7c8cff; }
QLabel#h1 { font-size: 22px; font-weight: 600; color: #1f2437; }
QLabel#muted { color: #6b7280; }
QFrame#card { background: white; border: 1px solid #e3e6ef; border-radius: 10px; }
QLabel#statNum { font-size: 26px; font-weight: 600; color: #3b4bd8; }
QPushButton { background: white; border: 1px solid #cfd4e4; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { background: #eef0fb; }
QPushButton#primary { background: #4256e8; color: white; border: none; }
QPushButton#primary:hover { background: #3647c9; }
QPushButton:disabled { color: #9aa0b4; background: #f0f1f6; }
QLineEdit, QComboBox, QSpinBox, QDateEdit, QPlainTextEdit, QTextBrowser, QTableWidget, QListWidget {
  background: white; border: 1px solid #d5d9e8; border-radius: 6px; padding: 4px; }
QTableWidget { gridline-color: #eceef6; }
QHeaderView::section { background: #eef0f8; border: none; padding: 6px; font-weight: 600; }
QStatusBar QLabel { padding: 0 8px; }
"""

PRIVACY_LOCAL = "background:#e7f6ec;color:#146c2e;border-radius:6px;padding:4px 10px;"
PRIVACY_EXTERNAL = "background:#fff3d6;color:#8a5a00;border-radius:6px;padding:4px 10px;"


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def short_date(iso: str) -> str:
    return iso[:16].replace("T", " ")


def doc_link(doc_id: int, page: int, query: str = "") -> str:
    return f"kv://doc/{doc_id}/{page}?q={quote(query)}"


def parse_doc_link(url: QUrl) -> tuple[int, int, str] | None:
    u = urlparse(url.toString())
    m = re.fullmatch(r"/(\d+)/(\d+)", u.path)
    if u.scheme != "kv" or u.netloc != "doc" or not m:
        return None
    q = parse_qs(u.query).get("q", [""])[0]
    return int(m.group(1)), int(m.group(2)), q


def esc(s: str) -> str:
    return html.escape(s or "")
