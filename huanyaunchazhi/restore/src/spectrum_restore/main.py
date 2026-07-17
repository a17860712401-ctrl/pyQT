from __future__ import annotations

import sys
from collections.abc import Sequence

from PyQt6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def build_application(arguments: Sequence[str] | None = None) -> tuple[QApplication, MainWindow]:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(list(arguments or sys.argv))
    app.setApplicationName("光谱还原")
    app.setOrganizationName("SpectrumTools")
    window = MainWindow()
    return app, window


def main() -> int:
    app, window = build_application()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
