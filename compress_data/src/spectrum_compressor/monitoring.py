from __future__ import annotations

import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .compression import compress_file
from .storage import StateStore

LogCallback = Callable[[str, str], None]
StatusCallback = Callable[[dict[str, int]], None]


@dataclass(slots=True)
class _Observation:
    size: int
    mtime_ns: int
    unchanged_count: int


class FileStabilityTracker:
    """Require repeated unchanged metadata before a file is consumed."""

    def __init__(self, required_observations: int = 2) -> None:
        if required_observations < 2:
            raise ValueError("required_observations 至少为 2")
        self.required_observations = required_observations
        self._observations: dict[str, _Observation] = {}

    def observe(self, path: Path | str, size: int, mtime_ns: int) -> bool:
        key = str(Path(path))
        previous = self._observations.get(key)
        if previous is None or previous.size != size or previous.mtime_ns != mtime_ns:
            self._observations[key] = _Observation(size, mtime_ns, 1)
            return False
        previous.unchanged_count += 1
        return previous.unchanged_count >= self.required_observations

    def forget(self, path: Path | str) -> None:
        self._observations.pop(str(Path(path)), None)


def scan_txt_files(directory: Path | str, *, sort_by_time: bool = True) -> list[Path]:
    """Return regular txt files in deterministic discovery order."""

    root = Path(directory)
    files = [path for path in root.iterdir() if path.is_file() and path.suffix.casefold() == ".txt"]
    if not sort_by_time:
        return sorted(files, key=lambda path: (path.name.casefold(), path.name))

    def sort_key(path: Path) -> tuple[int, str, str]:
        metadata = path.stat()
        birthtime_ns = getattr(metadata, "st_birthtime_ns", None)
        if birthtime_ns is None:
            birthtime_ns = metadata.st_ctime_ns if sys.platform == "win32" else metadata.st_mtime_ns
        return int(birthtime_ns), path.name.casefold(), path.name

    return sorted(files, key=sort_key)


class ProcessingService:
    """Poll input/output folders and isolate every file operation."""

    def __init__(
        self,
        input_directory: Path | str,
        output_directory: Path | str,
        store: StateStore,
        stop_event: threading.Event,
        *,
        scan_interval_seconds: float = 1.0,
        stability_observations: int = 2,
        log_callback: LogCallback | None = None,
        status_callback: StatusCallback | None = None,
    ) -> None:
        if scan_interval_seconds <= 0:
            raise ValueError("扫描间隔必须大于 0")
        self.input_directory = Path(input_directory)
        self.output_directory = Path(output_directory)
        self.store = store
        self.stop_event = stop_event
        self.scan_interval_seconds = scan_interval_seconds
        self.input_stability = FileStabilityTracker(stability_observations)
        self.output_stability = FileStabilityTracker(stability_observations)
        self.log_callback = log_callback or _default_log_callback
        self.status_callback = status_callback or (lambda _counts: None)
        self._known_inputs: set[str] = set()
        self._known_outputs: set[str] = set()

    def run(self) -> None:
        self._log("INFO", "文件监控与压缩任务已启动")
        while not self.stop_event.is_set():
            try:
                self.scan_once()
            except Exception as error:
                self._log("ERROR", f"目录扫描异常，将自动重试：{error}")
            self.stop_event.wait(self.scan_interval_seconds)
        self._log("INFO", "文件监控与压缩任务已停止")

    def scan_once(self) -> None:
        self.output_directory.mkdir(parents=True, exist_ok=True)
        input_files = scan_txt_files(self.input_directory)
        for path in input_files:
            path_key = _path_key(path)
            if path_key in self._known_inputs:
                continue
            try:
                metadata = path.stat()
                record = self.store.register_input(path, metadata.st_size, metadata.st_mtime_ns)
                self._known_inputs.add(path_key)
                if record.newly_registered:
                    selection = "已选中" if record.selected else "跳过"
                    self._log("DEBUG", f"输入序号 {record.sequence}（{selection}）：{path.name}")
            except Exception as error:
                self._log("ERROR", f"登记输入文件失败 {path.name}：{error}")

        for record in self.store.waiting_inputs():
            path = Path(record.path)
            try:
                metadata = path.stat()
                if not self.input_stability.observe(path, metadata.st_size, metadata.st_mtime_ns):
                    continue
                result = compress_file(path, self.output_directory)
                self.store.mark_input_compressed(path, result.output_path)
                self.store.register_output(result.output_path)
                self._known_outputs.add(_path_key(result.output_path))
                self.input_stability.forget(path)
                self._log(
                    "INFO",
                    f"压缩完成 {path.name}：{result.input_points} 点保留 {result.kept_points} 点",
                )
            except FileNotFoundError:
                self.input_stability.forget(path)
                self._log("WARNING", f"等待中的输入文件暂时不存在：{path}")
            except Exception as error:
                self.store.mark_input_failed(path, str(error))
                self.input_stability.forget(path)
                self._log("ERROR", f"压缩失败 {path.name}：{error}")

        for path in scan_txt_files(self.output_directory):
            path_key = _path_key(path)
            if path_key in self._known_outputs:
                continue
            try:
                metadata = path.stat()
                if self.output_stability.observe(path, metadata.st_size, metadata.st_mtime_ns):
                    self.store.register_output(path)
                    self._known_outputs.add(path_key)
                    self.output_stability.forget(path)
            except Exception as error:
                self._log("ERROR", f"登记输出文件失败 {path.name}：{error}")

        self.status_callback(self.store.counts())

    def _log(self, level: str, message: str) -> None:
        self.log_callback(level, message)


def _default_log_callback(level: str, message: str) -> None:
    logging.getLogger(__name__).log(getattr(logging, level, logging.INFO), message)


def _path_key(path: Path | str) -> str:
    return str(Path(path).resolve(strict=False))
