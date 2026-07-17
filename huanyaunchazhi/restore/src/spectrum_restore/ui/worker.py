from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from ..models import FileFailure
from ..restoration import restore_file


class RestoreWorker(QObject):
    progress = pyqtSignal(int, int, str)
    file_succeeded = pyqtSignal(object)
    file_failed = pyqtSignal(object)
    finished = pyqtSignal(int, int)

    def __init__(
        self,
        template_path: Path,
        compressed_paths: tuple[Path, ...],
        output_directory: Path,
    ) -> None:
        super().__init__()
        self.template_path = template_path
        self.compressed_paths = compressed_paths
        self.output_directory = output_directory

    @pyqtSlot()
    def run(self) -> None:
        successes = 0
        failures = 0
        total = len(self.compressed_paths)

        for position, source in enumerate(self.compressed_paths, start=1):
            try:
                result = restore_file(self.template_path, source, self.output_directory)
            except Exception as error:
                failures += 1
                self.file_failed.emit(FileFailure(source, str(error)))
            else:
                successes += 1
                self.file_succeeded.emit(result)
            self.progress.emit(position, total, source.name)
        self.finished.emit(successes, failures)
