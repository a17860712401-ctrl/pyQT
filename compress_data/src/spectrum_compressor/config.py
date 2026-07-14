from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .models import SerialSettings

APP_DIRECTORY_NAME = "SpectrumCompressor"


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Persisted user settings."""

    input_directory: str = ""
    output_directory: str = ""
    scan_interval_seconds: float = 1.0
    serial: SerialSettings = field(default_factory=SerialSettings)
    window_geometry: str = ""


def user_config_directory() -> Path:
    """Return an operating-system-appropriate writable configuration path."""

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_DIRECTORY_NAME


def default_config_path() -> Path:
    return user_config_directory() / "config.json"


def default_state_path() -> Path:
    return user_config_directory() / "state.sqlite3"


def default_log_path() -> Path:
    return user_config_directory() / "logs" / "application.log"


class ConfigManager:
    """Load and atomically save application settings."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_config_path()

    def load(self) -> AppConfig:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return AppConfig()
        if not isinstance(data, dict):
            return AppConfig()
        return _config_from_mapping(data)

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_name = stream.name
                json.dump(asdict(config), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, self.path)
        except Exception:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)
            raise


def _config_from_mapping(data: dict[str, Any]) -> AppConfig:
    defaults = AppConfig()
    serial_data = data.get("serial")
    if not isinstance(serial_data, dict):
        serial_data = {}

    serial_defaults = defaults.serial
    port = _string_value(serial_data.get("port"), serial_defaults.port)
    baudrate = _integer_choice(serial_data.get("baudrate"), serial_defaults.baudrate, minimum=1)
    bytesize = _choice(serial_data.get("bytesize"), serial_defaults.bytesize, {5, 6, 7, 8})
    parity = _choice(serial_data.get("parity"), serial_defaults.parity, {"N", "E", "O", "M", "S"})
    stopbits = _numeric_choice(serial_data.get("stopbits"), serial_defaults.stopbits, {1.0, 1.5, 2.0})
    scan_interval = _positive_float(data.get("scan_interval_seconds"), defaults.scan_interval_seconds)

    return AppConfig(
        input_directory=_string_value(data.get("input_directory"), defaults.input_directory),
        output_directory=_string_value(data.get("output_directory"), defaults.output_directory),
        scan_interval_seconds=scan_interval,
        serial=SerialSettings(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
        ),
        window_geometry=_string_value(data.get("window_geometry"), defaults.window_geometry),
    )


def _string_value(value: object, default: str) -> str:
    return value if isinstance(value, str) else default


def _integer_choice(value: object, default: int, *, minimum: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= minimum else default


def _choice(value: object, default: Any, choices: set[Any]) -> Any:
    try:
        return value if value in choices else default
    except TypeError:
        return default


def _numeric_choice(value: object, default: float, choices: set[float]) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) in choices:
        return float(value)
    return default


def _positive_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0:
        return float(value)
    return default
