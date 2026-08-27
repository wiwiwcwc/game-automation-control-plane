from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import AppPaths


def configure_app_logging(paths: AppPaths) -> logging.Logger:
    paths.ensure()
    logger = logging.getLogger("game_control_plane")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers):
        handler = RotatingFileHandler(
            paths.app_log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=4,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
    return logger
