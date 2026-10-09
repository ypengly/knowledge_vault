"""Headless smoke test of the Qt UI. Skipped automatically if PySide6 is not installed."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

from .helpers import make_vault, write


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TestUI(unittest.TestCase):
    def test_main_window_builds_and_shows_data(self):
        from knowledge_vault import ingest
        from knowledge_vault.ui import workers
        from knowledge_vault.ui.main_window import MainWindow
        app = QApplication.instance() or QApplication([])
        workers.init()
        v, tmp = make_vault()
        ingest.import_file(v, write(tmp, "a.txt", "Customer retention drives growth in subscription businesses."))
        win = MainWindow(v)
        win.library.refresh()
        self.assertEqual(win.library.table.rowCount(), 1)
        win.search.query.setText("retention")
        hits = v.search("retention")
        win.search._show("retention", hits)
        self.assertIn("a.txt", win.search.out.toPlainText())
        ans = v.ask("customer retention", use_llm=False)
        win.chat._render("customer retention", ans)
        self.assertIn("Source:", win.chat.view.toPlainText())
        win.chat._render("zzz", __import__("knowledge_vault.qa", fromlist=["x"]).ask(v, "zzz qqq"))
        self.assertIn("couldn't find enough information", win.chat.view.toPlainText())


if __name__ == "__main__":
    unittest.main()
