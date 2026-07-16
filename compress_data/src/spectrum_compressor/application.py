from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from .config import default_log_path
from .logging_setup import reset_application_logging
from .models import SerialSettings
from .monitoring import ProcessingService, scan_txt_files

from .serial_comm import SerialPortInfo, SerialWorker, list_serial_ports
from .storage import StateStore


class ApplicationController(QObject):
    """Coordinate worker threads and expose thread-safe Qt signals."""

    log_message = pyqtSignal(str, str)
    counts_changed = pyqtSignal(dict)
    task_state_changed = pyqtSignal(bool, str)
    serial_state_changed = pyqtSignal(bool, str)

    def __init__(
        self,
        store: StateStore,
        *,
        serial_worker_factory: Callable[..., SerialWorker] = SerialWorker,
    ) -> None:
        super().__init__()
        self.store = store
        self._serial_worker_factory = serial_worker_factory
        self._serial_worker: SerialWorker | None = None
        self._serial_thread: threading.Thread | None = None
        self._processing_service: ProcessingService | None = None
        self._processing_thread: threading.Thread | None = None
        self._processing_stop = threading.Event()
        self._state_lock = threading.RLock()

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._processing_thread is not None and self._processing_thread.is_alive()

    @property
    def is_serial_open(self) -> bool:
        with self._state_lock:
            return self._serial_worker is not None and self._serial_worker.is_open

    @property
    def processing_thread(self) -> threading.Thread | None:
        with self._state_lock:
            return self._processing_thread

    def available_ports(self) -> list[SerialPortInfo]:
        return list_serial_ports()

    def start_tasks(
        self,
        input_directory: Path | str,
        output_directory: Path | str,
        *,
        scan_interval_seconds: float = 1.0,
    ) -> None:
        input_path = Path(input_directory).expanduser().resolve(strict=False)
        output_path = Path(output_directory).expanduser().resolve(strict=False)
        if not input_path.is_dir():
            raise ValueError("输入文件夹不存在或不可访问")
        if input_path == output_path:
            raise ValueError("输入文件夹和输出文件夹不能相同")
        output_path.mkdir(parents=True, exist_ok=True)

        with self._state_lock:
            if self._processing_thread is not None and self._processing_thread.is_alive():
                return
            self._processing_stop = threading.Event()
            self._processing_service = ProcessingService(
                input_path,
                output_path,
                self.store,
                self._processing_stop,
                scan_interval_seconds=scan_interval_seconds,
                log_callback=self._emit_log,
                status_callback=self._emit_counts,
            )
            self._processing_thread = threading.Thread(
                target=self._processing_entry,
                name="spectrum-processing",
                daemon=True,
            )
            thread = self._processing_thread
        thread.start()
        self.task_state_changed.emit(True, "任务运行中")
        self._emit_log("INFO", f"任务已启动：{input_path} → {output_path}")

    def stop_tasks(self, *, timeout: float = 5.0) -> bool:
        with self._state_lock:
            thread = self._processing_thread
            self._processing_stop.set()
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout)
        stopped = thread is None or not thread.is_alive()
        if stopped:
            with self._state_lock:
                if self._processing_thread is thread:
                    self._processing_thread = None
                    self._processing_service = None
            self.task_state_changed.emit(False, "任务已停止")
        else:
            self._emit_log("WARNING", "后台处理线程未在超时时间内停止")
        return stopped

    def open_serial(self, settings: SerialSettings) -> None:
        self._ensure_serial_thread()
        with self._state_lock:
            worker = self._serial_worker
        if worker is not None:
            worker.request_open(settings)

    def close_serial(self) -> None:
        with self._state_lock:
            worker = self._serial_worker
        if worker is not None:
            worker.request_close()

    def refresh_counts(self) -> dict[str, int]:
        counts = self.store.counts()
        self.counts_changed.emit(counts)
        return counts
    
    def reset_all_data(
        self,
        input_directory: Path | str,
        output_directory: Path | str,
        *,
        log_path: Path | str | None = None,
    ) -> tuple[int, int]:
        """删除工作文件和全部历史记录，让软件重新开始计数。"""

        input_path = Path(input_directory).expanduser().resolve(strict=False)
        output_path = Path(output_directory).expanduser().resolve(strict=False)

        with self._state_lock:
            processing_running = (
                self._processing_thread is not None
                and self._processing_thread.is_alive()
            )
            serial_open = (
                self._serial_worker is not None
                and self._serial_worker.is_open
            )

        if processing_running:
            raise RuntimeError("请先手动停止处理任务")

        if serial_open:
            raise RuntimeError("请先手动关闭串口")

        if not input_path.is_dir():
            raise ValueError("输入文件夹不存在或不可访问")

        if not output_path.is_dir():
            raise ValueError("输出文件夹不存在或不可访问")

        if input_path == output_path:
            raise ValueError("输入文件夹和输出文件夹不能相同")

        input_txt_files = scan_txt_files(input_path, sort_by_time=False)
        output_txt_files = scan_txt_files(output_path, sort_by_time=False)

        for file_path in input_txt_files:
            file_path.unlink()

        for file_path in output_txt_files:
            file_path.unlink()

        self.store.reset_all()
        reset_application_logging(log_path or default_log_path())

        counts = self.store.counts()
        self.counts_changed.emit(counts)

        return len(input_txt_files), len(output_txt_files)

    def shutdown(self, *, timeout: float = 5.0) -> bool:
        processing_stopped = self.stop_tasks(timeout=timeout)
        with self._state_lock:
            worker = self._serial_worker
            serial_thread = self._serial_thread
        if worker is not None:
            worker.stop()
        if serial_thread is not None and serial_thread.is_alive() and serial_thread is not threading.current_thread():
            serial_thread.join(timeout)
        serial_stopped = serial_thread is None or not serial_thread.is_alive()
        if not serial_stopped:
            self._emit_log("WARNING", "串口线程未在超时时间内停止")
        return processing_stopped and serial_stopped

    def _ensure_serial_thread(self) -> None:
        with self._state_lock:
            if self._serial_thread is not None and self._serial_thread.is_alive():
                return
            self._serial_worker = self._serial_worker_factory(
                self.store,
                log_callback=self._emit_log,
                status_callback=self._emit_serial_state,
                counts_callback=self._emit_counts,
            )
            self._serial_thread = threading.Thread(
                target=self._serial_worker.run,
                name="serial-sender",
                daemon=True,
            )
            thread = self._serial_thread
        thread.start()

    def _processing_entry(self) -> None:
        try:
            with self._state_lock:
                service = self._processing_service
            if service is not None:
                service.run()
        except Exception as error:
            self._emit_log("ERROR", f"处理线程意外退出：{error}")
        finally:
            self.task_state_changed.emit(False, "任务已停止")

    def _emit_log(self, level: str, message: str) -> None:
        logging.getLogger("spectrum_compressor").log(getattr(logging, level, logging.INFO), message)
        self.log_message.emit(level, message)

    def _emit_counts(self, counts: dict[str, int]) -> None:
        self.counts_changed.emit(counts)

    def _emit_serial_state(self, opened: bool, message: str) -> None:
        self.serial_state_changed.emit(opened, message)
