from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .compression_contract import (
    ANCHOR_WAVENUMBERS,
    DOWNSAMPLE_STRIDE,
    NEIGHBORHOOD_RADIUS,
    select_indexes,
)
from .formatting import format_intensity
from .interpolation import interpolate_with_fallback
from .models import FileFailure, RestoreResult, TemplateAxis
from .parsing import parse_compressed, parse_template


class RestoreError(ValueError):
    """Raised when a compressed file cannot be restored against its template."""


def _restore_values(
    axis: TemplateAxis,
    intensities: Sequence[int],
    *,
    anchors: Sequence[float],
    radius: int,
    stride: int,
) -> tuple[tuple[int | float, ...], tuple[int, ...], str, tuple[str, ...]]:
    indexes = select_indexes(axis.values, anchors=anchors, radius=radius, stride=stride)
    if len(intensities) != len(indexes):
        raise RestoreError(
            f"压缩强度数量为 {len(intensities)}，模板规则要求 {len(indexes)} 个，"
            "请检查模板是否与压缩前光谱一致"
        )

    known = sorted(
        (axis.values[index], float(value))
        for index, value in zip(indexes, intensities)
    )
    restored, method, warnings = interpolate_with_fallback(
        tuple(item[0] for item in known),
        tuple(item[1] for item in known),
        axis.values,
    )
    result: list[int | float] = list(restored)
    for index, value in zip(indexes, intensities):
        result[index] = int(value)
    return tuple(result), indexes, method, warnings


def _write_output(
    axis: TemplateAxis,
    values: Sequence[int | float],
    source_path: Path,
    output_directory: Path,
) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f"{source_path.stem}_restored.txt"
    temporary_name: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=output_directory,
            prefix=f".{source_path.stem}_restored.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            for raw_x, intensity in zip(axis.raw_values, values):
                temporary.write(f"{raw_x},{format_intensity(intensity)}\r\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, output_path)
    except OSError as error:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise RestoreError(f"无法保存还原文件 {output_path.name}：{error}") from error
    return output_path


def restore_file(
    template_path: Path | str,
    compressed_path: Path | str,
    output_directory: Path | str,
    *,
    anchors: Sequence[float] = ANCHOR_WAVENUMBERS,
    radius: int = NEIGHBORHOOD_RADIUS,
    stride: int = DOWNSAMPLE_STRIDE,
) -> RestoreResult:
    source = Path(compressed_path)
    output_dir = Path(output_directory)
    axis = parse_template(template_path)
    intensities = parse_compressed(source)
    values, _indexes, method, warnings = _restore_values(
        axis,
        intensities,
        anchors=anchors,
        radius=radius,
        stride=stride,
    )
    output_path = _write_output(axis, values, source, output_dir)
    return RestoreResult(source, output_path, len(values), method, warnings)


def restore_batch(
    template_path: Path | str,
    compressed_paths: Sequence[Path | str],
    output_directory: Path | str,
    *,
    anchors: Sequence[float] = ANCHOR_WAVENUMBERS,
    radius: int = NEIGHBORHOOD_RADIUS,
    stride: int = DOWNSAMPLE_STRIDE,
) -> tuple[tuple[RestoreResult, ...], tuple[FileFailure, ...]]:
    parse_template(template_path)
    successes: list[RestoreResult] = []
    failures: list[FileFailure] = []

    for path in compressed_paths:
        source = Path(path)
        try:
            result = restore_file(
                template_path,
                source,
                output_directory,
                anchors=anchors,
                radius=radius,
                stride=stride,
            )
        except Exception as error:
            failures.append(FileFailure(source, str(error)))
        else:
            successes.append(result)
    return tuple(successes), tuple(failures)
