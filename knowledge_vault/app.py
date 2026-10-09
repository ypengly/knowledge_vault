from __future__ import annotations

import sys


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from .core import Vault
    from .ui import workers
    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Knowledge Vault")
    workers.init()
    vault = Vault()
    win = MainWindow(vault)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
