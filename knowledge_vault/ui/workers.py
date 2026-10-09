"""Background execution. Results are marshalled back to the GUI thread through a
QObject slot, so UI code in callbacks is always safe."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _Dispatcher(QObject):
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run)

    @Slot(object)
    def _run(self, fn):
        fn()


_dispatcher: _Dispatcher | None = None
general_pool = QThreadPool()
ingest_pool = QThreadPool()
ingest_pool.setMaxThreadCount(1)  # serialise embedding/index writes


def init() -> None:
    """Call once from the GUI thread after QApplication exists."""
    global _dispatcher
    _dispatcher = _Dispatcher()


def post(fn: Callable[[], None]) -> None:
    if _dispatcher is not None:
        _dispatcher.call.emit(fn)


class _Task(QRunnable):
    def __init__(self, fn, on_done, on_error):
        super().__init__()
        self.fn, self.on_done, self.on_error = fn, on_done, on_error

    def run(self):
        try:
            result = self.fn()
        except Exception as e:  # noqa: BLE001 - surfaced to the UI
            err = e
            if self.on_error:
                post(lambda: self.on_error(err))
            return
        if self.on_done:
            post(lambda: self.on_done(result))


def run_async(fn, on_done=None, on_error=None, pool: QThreadPool | None = None) -> None:
    (pool or general_pool).start(_Task(fn, on_done, on_error))
