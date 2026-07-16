from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "spectrum_compressor"


def configure_logging(log_path: Path | str) -> logging.Logger:
    """Configure bounded file logging and a concise console stream."""

    close_application_logging()
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(threadName)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def close_application_logging() -> None:
    """Flush and close application handlers, primarily for clean shutdown/tests."""

    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        try:
            handler.flush()
            handler.close()
        finally:
            logger.removeHandler(handler)


def reset_application_logging(log_path: Path | str) -> logging.Logger:
    """删除当前日志及全部轮换日志，然后重新启用空日志。"""

    close_application_logging()

    path = Path(log_path)
    log_files = [path]

    if path.parent.exists():
        for candidate in path.parent.glob(f"{path.name}.*"):
            rotated_suffix = candidate.name[len(path.name) + 1 :]
            if candidate.is_file() and rotated_suffix.isdigit():
                log_files.append(candidate)

    for log_file in log_files:
        log_file.unlink(missing_ok=True)

    return configure_logging(path)

