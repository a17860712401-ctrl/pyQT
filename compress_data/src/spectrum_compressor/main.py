from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Sequence

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication, QMessageBox

from .application import ApplicationController
from .config import ConfigManager, default_config_path, default_log_path, default_state_path
from .logging_setup import close_application_logging, configure_logging
from .storage import StateStore
from .ui.main_window import MainWindow


def build_application(
    *,
    config_path: Path | str | None = None,
    state_path: Path | str | None = None,
    arguments: Sequence[str] | None = None,
) -> tuple[QApplication, ApplicationController, MainWindow]:
    """Construct the application graph without entering the event loop."""

    application = QApplication.instance()
    if application is None:
        application = QApplication(list(arguments) if arguments is not None else sys.argv)
    application.setApplicationName("光谱压缩串口上位机")
    application.setOrganizationName("SpectrumCompressor")
    _configure_application_font(application)
    config_manager = ConfigManager(config_path or default_config_path())
    store = StateStore(state_path or default_state_path())
    controller = ApplicationController(store)
    window = MainWindow(controller, config_manager)
    return application, controller, window


def _configure_application_font(application: QApplication) -> None:
    if sys.platform == "win32":
        application.setFont(QFont("Microsoft YaHei UI", 10))
        return
    if sys.platform == "darwin":
        application.setFont(QFont("PingFang SC", 10))
        return
    available = set(QFontDatabase.families())
    for family in ("Noto Sans CJK SC", "WenQuanYi Micro Hei", "Source Han Sans SC", "DejaVu Sans"):
        if family in available:
            application.setFont(QFont(family, 10))
            return


def main() -> int:
    """Run the PyQt6 desktop application."""

    logger = configure_logging(default_log_path())

    def handle_uncaught_exception(exception_type, exception, traceback) -> None:
        logger.critical("主线程发生未捕获异常", exc_info=(exception_type, exception, traceback))
        QMessageBox.critical(None, "程序异常", f"程序发生未捕获异常：\n{exception}")

    sys.excepthook = handle_uncaught_exception
    try:
        application, controller, window = build_application()
        window.show()
        logger.info("应用程序已启动")
        result = application.exec()
        controller.shutdown(timeout=5)
        logger.info("应用程序正常退出，返回码 %s", result)
        return int(result)
    except Exception:
        logging.getLogger("spectrum_compressor").exception("应用程序启动失败")
        raise
    finally:
        close_application_logging()


if __name__ == "__main__":
    raise SystemExit(main())
