from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QProgressDialog, QWidget

from ..integrations.maa_preflight import MaaPreflightReport, run_maa_preflight
from ..integrations.fos_preflight import run_fos_preflight
from ..integrations.onedragon_preflight import run_onedragon_preflight
from .i18n import (
    LanguageManager,
    fos_preflight_progress_text,
    onedragon_preflight_progress_text,
    preflight_progress_text,
)


class _MaaPreflightWorker(QObject):
    progress = Signal(str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, config: dict[str, object], kind: str = "maa"):
        super().__init__()
        self.config = config
        self.kind = kind

    @Slot()
    def run(self) -> None:
        try:
            check = {
                "fos": run_fos_preflight,
                "onedragon": run_onedragon_preflight,
            }.get(self.kind, run_maa_preflight)
            report = check(self.config, progress=self.progress.emit)
        except Exception as exc:  # pragma: no cover - defensive thread boundary
            self.failed.emit(str(exc) or "The setup check failed unexpectedly.")
            return
        self.completed.emit(report)


class _MaaProgressDialog(QProgressDialog):
    """A modal progress window that only the completed worker can dismiss."""

    def __init__(self, parent: QWidget | None, i18n: LanguageManager):
        super().__init__(i18n.text("preflight.checking"), "", 0, 0, parent)
        self._finished = False

    def finish(self, result: int) -> None:
        self._finished = True
        self.done(result)

    def reject(self) -> None:
        if self._finished:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._finished:
            super().closeEvent(event)
        else:
            event.ignore()


class _MaaPreflightController(QObject):
    """Receive worker signals on the GUI thread and close the modal dialog."""

    def __init__(
        self,
        dialog: _MaaProgressDialog,
        thread: QThread,
        i18n: LanguageManager,
        kind: str = "maa",
    ):
        super().__init__()
        self.dialog = dialog
        self.thread = thread
        self.i18n = i18n
        self.kind = kind
        self.report: MaaPreflightReport | None = None
        self.error: str | None = None

    @Slot(str)
    def progress(self, message: str) -> None:
        translate = {
            "fos": fos_preflight_progress_text,
            "onedragon": onedragon_preflight_progress_text,
        }.get(self.kind, preflight_progress_text)
        self.dialog.setLabelText(translate(self.i18n, message))

    @Slot(object)
    def completed(self, report: MaaPreflightReport) -> None:
        self.report = report
        self.thread.quit()
        self.dialog.finish(1)

    @Slot(str)
    def failed(self, message: str) -> None:
        self.error = message
        self.thread.quit()
        self.dialog.finish(0)


def run_preflight_with_progress(
    config: dict[str, object],
    parent: QWidget | None = None,
    i18n: LanguageManager | None = None,
    kind: str = "maa",
) -> tuple[MaaPreflightReport | None, str | None]:
    """Run the blocking probes on a worker thread while Qt remains responsive."""

    language = i18n or LanguageManager(persist=False)
    dialog = _MaaProgressDialog(parent, language)
    prefix = {
        "fos": "fos_preflight",
        "onedragon": "onedragon_preflight",
    }.get(kind, "preflight")
    dialog.setLabelText(language.text(f"{prefix}.checking"))
    dialog.setWindowTitle(language.text(f"{prefix}.progress_title"))
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setCancelButton(None)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)

    thread = QThread()
    worker = _MaaPreflightWorker(dict(config), kind=kind)
    worker.moveToThread(thread)
    controller = _MaaPreflightController(dialog, thread, language, kind=kind)

    thread.started.connect(worker.run)
    worker.progress.connect(controller.progress)
    worker.completed.connect(controller.completed)
    worker.failed.connect(controller.failed)
    worker.completed.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.start()
    dialog.exec()
    thread.quit()
    thread.wait()
    dialog.deleteLater()
    thread.deleteLater()
    return controller.report, controller.error


__all__ = ["run_preflight_with_progress"]
