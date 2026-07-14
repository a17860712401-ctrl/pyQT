from __future__ import annotations

import logging
import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .models import SerialSettings
from .storage import OutputRecord, StateStore

LogCallback = Callable[[str, str], None]
SerialStatusCallback = Callable[[bool, str], None]
StatusCallback = Callable[[dict[str, int]], None]
SerialFactory = Callable[..., "SerialLike"]
_HEX_LINE = re.compile(r"^(?:[0-9A-Fa-f]{2}){1,4}$")


class SerialLike(Protocol):
    is_open: bool

    def write(self, payload: bytes) -> int: ...

    def flush(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SerialPortInfo:
    device: str
    description: str


class HexPayloadError(ValueError):
    """Raised when a compressed output file is not valid whole-byte hex text."""


def load_hex_payload(path: Path | str) -> bytes:
    """Decode one compressed text file to raw serial bytes."""

    payload = bytearray()
    with Path(path).open("r", encoding="utf-8-sig") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            line = raw_line.strip()
            if not line:
                continue
            if _HEX_LINE.fullmatch(line) is None:
                raise HexPayloadError(
                    f"第 {line_number} 行不是 2、4、6 或 8 位十六进制数据"
                )
            payload.extend(bytes.fromhex(line))
    if not payload:
        raise HexPayloadError("压缩文件中没有可发送的十六进制数据")
    return bytes(payload)


def list_serial_ports() -> list[SerialPortInfo]:
    """List ports without making pyserial an import-time requirement."""

    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    ports = [SerialPortInfo(port.device, port.description or port.device) for port in list_ports.comports()]
    return sorted(ports, key=lambda item: item.device.casefold())


class SerialWorker:
    """Own the serial object and drain the persistent output queue."""

    def __init__(
        self,
        store: StateStore,
        *,
        serial_factory: SerialFactory | None = None,
        minimum_file_interval: float = 1.0,
        poll_interval: float = 0.2,
        log_callback: LogCallback | None = None,
        status_callback: SerialStatusCallback | None = None,
        counts_callback: StatusCallback | None = None,
    ) -> None:
        self.store = store
        self.serial_factory = serial_factory or _default_serial_factory
        self.minimum_file_interval = minimum_file_interval
        self.poll_interval = poll_interval
        self.log_callback = log_callback or _default_log_callback
        self.status_callback = status_callback or (lambda _opened, _message: None)
        self.counts_callback = counts_callback or (lambda _counts: None)
        self._commands: queue.Queue[tuple[str, SerialSettings | None]] = queue.Queue()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._serial: SerialLike | None = None
        self._last_send_started: float | None = None
        self._state_lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._state_lock:
            serial_port = self._serial
            return serial_port is not None and bool(getattr(serial_port, "is_open", True))

    def request_open(self, settings: SerialSettings) -> None:
        self._commands.put(("open", settings))
        self._wake_event.set()

    def request_close(self) -> None:
        self._commands.put(("close", None))
        self._wake_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()

    def run(self) -> None:
        self._log("INFO", "串口发送线程已启动")
        try:
            while not self._stop_event.is_set():
                self._process_commands()
                wait_seconds = self.send_next_once()
                self._wake_event.wait(max(0.01, min(wait_seconds, self.poll_interval)))
                self._wake_event.clear()
        finally:
            self.close_connection()
            self._log("INFO", "串口发送线程已停止")

    def open_connection(self, settings: SerialSettings) -> None:
        if not settings.port:
            raise ValueError("请选择串口")
        self.close_connection(notify=False)
        try:
            serial_port = self.serial_factory(
                port=settings.port,
                baudrate=settings.baudrate,
                bytesize=settings.bytesize,
                parity=settings.parity,
                stopbits=settings.stopbits,
                timeout=1,
                write_timeout=5,
            )
        except Exception as error:
            self.status_callback(False, f"打开失败：{error}")
            self._log("ERROR", f"串口 {settings.port} 打开失败：{error}")
            raise
        with self._state_lock:
            self._serial = serial_port
            self._last_send_started = None
        self.status_callback(True, f"已打开 {settings.port}")
        self._log("INFO", f"串口已打开：{settings.port} @ {settings.baudrate}")

    def close_connection(self, *, notify: bool = True) -> None:
        with self._state_lock:
            serial_port = self._serial
            self._serial = None
            self._last_send_started = None
        if serial_port is not None:
            try:
                serial_port.close()
            except Exception as error:
                self._log("WARNING", f"关闭串口时发生异常：{error}")
        if notify:
            self.status_callback(False, "串口已关闭")

    def send_next_once(
        self,
        *,
        now: float | None = None,
        monotonic_now: float | None = None,
    ) -> float:
        """Try one queue item and return the recommended next wait duration."""

        current_time = time.time() if now is None else now
        current_monotonic = time.monotonic() if monotonic_now is None else monotonic_now
        with self._state_lock:
            serial_port = self._serial
            last_started = self._last_send_started
        if serial_port is None or not bool(getattr(serial_port, "is_open", True)):
            return self.poll_interval
        if last_started is not None:
            remaining = self.minimum_file_interval - (current_monotonic - last_started)
            if remaining > 0:
                return remaining

        record = self.store.next_pending_output(now=current_time)
        if record is None:
            return self.poll_interval
        try:
            payload = load_hex_payload(record.path)
        except HexPayloadError as error:
            self.store.mark_output_failed(record.id, str(error))
            self._log("ERROR", f"发送文件格式错误 {Path(record.path).name}：{error}")
            self.counts_callback(self.store.counts())
            return 0.0
        except OSError as error:
            return self._schedule_retry(record, error, current_time)

        with self._state_lock:
            self._last_send_started = current_monotonic
        try:
            written = serial_port.write(payload)
            if written != len(payload):
                raise OSError(f"串口仅写入 {written}/{len(payload)} 字节")
            serial_port.flush()
        except Exception as error:
            return self._schedule_retry(record, error, current_time)

        self.store.mark_output_sent(record.id, sent_at=current_time)
        self._log("INFO", f"发送完成 {Path(record.path).name}：{len(payload)} 字节")
        self.counts_callback(self.store.counts())
        return self.minimum_file_interval

    def _schedule_retry(self, record: OutputRecord, error: Exception, current_time: float) -> float:
        retry_delay = float(min(30, 2 ** min(record.attempts, 5)))
        self.store.mark_output_retry(
            record.id,
            str(error),
            next_attempt_at=current_time + retry_delay,
        )
        self._log(
            "WARNING",
            f"发送失败 {Path(record.path).name}，{retry_delay:g} 秒后重试：{error}",
        )
        self.counts_callback(self.store.counts())
        return max(self.minimum_file_interval, retry_delay)

    def _process_commands(self) -> None:
        while True:
            try:
                command, settings = self._commands.get_nowait()
            except queue.Empty:
                return
            try:
                if command == "open" and settings is not None:
                    self.open_connection(settings)
                elif command == "close":
                    self.close_connection()
            except Exception:
                continue

    def _log(self, level: str, message: str) -> None:
        self.log_callback(level, message)


def _default_serial_factory(**settings: Any) -> SerialLike:
    try:
        import serial
    except ImportError as error:
        raise RuntimeError("未安装 pyserial，请先执行 pip install -r requirements.txt") from error
    return serial.Serial(**settings)


def _default_log_callback(level: str, message: str) -> None:
    logging.getLogger(__name__).log(getattr(logging, level, logging.INFO), message)
