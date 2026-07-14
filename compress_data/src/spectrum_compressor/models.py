from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SpectrumPoint:
    """One parsed spectrum sample."""

    wavenumber: float
    intensity: Decimal


@dataclass(frozen=True, slots=True)
class CompressionResult:
    """Summary of one successfully compressed file."""

    source_path: Path
    output_path: Path
    input_points: int
    kept_points: int
    skipped_lines: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SerialSettings:
    """User-selectable serial port settings."""

    port: str = ""
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1.0
