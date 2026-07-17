from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TemplateAxis:
    raw_values: tuple[str, ...]
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class RestoreResult:
    source_path: Path
    output_path: Path
    point_count: int
    method: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FileFailure:
    source_path: Path
    message: str
