from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .platform.logging import configure_app_logging
from .platform.paths import DATA_DIR_ENV, app_paths
from .ui.main_window import MainWindow
from .ui.theme import apply_theme
from .integrations.maa_punish import INTERNAL_FOS_RUNNER_ARG


PACKAGED_SMOKE_ENV = "GAME_CONTROL_PLANE_PACKAGED_SMOKE"
PACKAGED_SMOKE_ARG = "--game-control-plane-packaged-smoke"
PACKAGED_SMOKE_DATA_ARG = "--game-control-plane-smoke-data="


def app_icon_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "game_control_plane" / "assets" / "app_icon.png"
    return Path(__file__).resolve().parent / "assets" / "app_icon.png"


def main() -> int:
    if INTERNAL_FOS_RUNNER_ARG in sys.argv:
        from .integrations.fos_runner import run_fos_runner_cli

        index = sys.argv.index(INTERNAL_FOS_RUNNER_ARG)
        return run_fos_runner_cli(sys.argv[index + 1 :])
    smoke_enabled = (
        os.environ.get(PACKAGED_SMOKE_ENV) == "1" or PACKAGED_SMOKE_ARG in sys.argv
    )
    original_data_dir = os.environ.get(DATA_DIR_ENV)
    smoke_data: tempfile.TemporaryDirectory[str] | None = None
    logger: logging.Logger | None = None
    smoke_data_argument = next(
        (
            argument.removeprefix(PACKAGED_SMOKE_DATA_ARG)
            for argument in sys.argv
            if argument.startswith(PACKAGED_SMOKE_DATA_ARG)
        ),
        "",
    )
    if smoke_enabled and smoke_data_argument:
        os.environ[DATA_DIR_ENV] = smoke_data_argument
    elif smoke_enabled and not original_data_dir:
        smoke_data = tempfile.TemporaryDirectory(prefix="game-control-plane-smoke-")
        os.environ[DATA_DIR_ENV] = smoke_data.name

    try:
        paths = app_paths().ensure()
        logger = configure_app_logging(paths)
        application = QApplication(sys.argv)
        application.setApplicationName("Hsiesta")
        application.setWindowIcon(QIcon(str(app_icon_path())))
        apply_theme(application)
        window = MainWindow(paths, logger=logger)
        window.show()

        def report_exception(exc_type, exc_value, exc_traceback):
            if exc_type is KeyboardInterrupt:
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            logger.critical("Unhandled application exception", exc_info=(exc_type, exc_value, exc_traceback))
            QMessageBox.critical(
                window,
                window.i18n.text("message.app_error_title"),
                window.i18n.text("message.app_error_body", path=paths.app_log_path),
            )

        sys.excepthook = report_exception
        if smoke_enabled:

            def finish_smoke() -> None:
                window.close()
                application.quit()

            QTimer.singleShot(1000, finish_smoke)
        return application.exec()
    finally:
        if smoke_data is not None:
            if logger is not None:
                for handler in list(logger.handlers):
                    handler.close()
                    logger.removeHandler(handler)
            smoke_data.cleanup()
        if original_data_dir is None:
            os.environ.pop(DATA_DIR_ENV, None)
        else:
            os.environ[DATA_DIR_ENV] = original_data_dir


if __name__ == "__main__":
    raise SystemExit(main())
