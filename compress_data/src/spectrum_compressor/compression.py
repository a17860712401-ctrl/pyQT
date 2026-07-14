from __future__ import annotations

import os
import re
import tempfile
from math import isfinite
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Sequence

from .models import CompressionResult, SpectrumPoint

ANCHOR_WAVENUMBERS = (200.0, 800.0, 1400.0, 2000.0, 2600.0, 3200.0, 3800.0, 4400.0)
NEIGHBORHOOD_RADIUS = 10
DOWNSAMPLE_STRIDE = 30
_SPLIT_PATTERN = re.compile(r"[,，\s]+")


class SpectrumFormatError(ValueError):
    """Raised when a spectrum file contains no usable samples."""


def parse_spectrum_lines(lines: Iterable[str]) -> tuple[list[SpectrumPoint], list[int]]:
    """Parse wavenumber and intensity pairs from text lines."""

    points: list[SpectrumPoint] = []
    skipped_lines: list[int] = []
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        fields = [field for field in _SPLIT_PATTERN.split(line) if field]
        if len(fields) < 2:
            skipped_lines.append(line_number)
            continue
        try:
            wavenumber = float(fields[0])
            intensity = Decimal(fields[1])
        except (ValueError, InvalidOperation):
            skipped_lines.append(line_number)
            continue
        if not isfinite(wavenumber) or not intensity.is_finite():
            skipped_lines.append(line_number)
            continue
        points.append(SpectrumPoint(wavenumber=wavenumber, intensity=intensity))

    if not points:
        raise SpectrumFormatError("光谱文件中没有可解析的“波数，强度”数据")
    return points, skipped_lines


def select_indexes(
    points: Sequence[SpectrumPoint],
    *,
    anchors: Sequence[float] = ANCHOR_WAVENUMBERS,
    radius: int = NEIGHBORHOOD_RADIUS,
    stride: int = DOWNSAMPLE_STRIDE,
) -> list[int]:
    """Select endpoint, downsampled, and anchor-neighborhood indexes."""

    if not points:
        return []
    if radius < 0:
        raise ValueError("radius 不能小于 0")
    if stride <= 0:
        raise ValueError("stride 必须大于 0")

    selected = set(range(0, len(points), stride))
    selected.update((0, len(points) - 1))
    minimum_wavenumber = min(point.wavenumber for point in points)
    maximum_wavenumber = max(point.wavenumber for point in points)

    for anchor in anchors:
        if not minimum_wavenumber <= anchor <= maximum_wavenumber:
            continue
        center = min(
            range(len(points)),
            key=lambda index: (abs(points[index].wavenumber - anchor), index),
        )
        start = max(0, center - radius)
        stop = min(len(points), center + radius + 1)
        selected.update(range(start, stop))

    return sorted(selected)


def encode_intensity(value: Decimal) -> str:
    """Round and encode one intensity as minimal unsigned whole bytes."""

    if value < 0:
        raise OverflowError("强度超出 32 位无符号整数范围")
    rounded = int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if rounded > 2**32 - 1:
        raise OverflowError("强度超出 32 位无符号整数范围")
    encoded = format(rounded, "x")
    width = max(2, len(encoded) + len(encoded) % 2)
    return encoded.zfill(width)


def compress_file(
    source_path: Path | str,
    output_directory: Path | str,
    *,
    anchors: Sequence[float] = ANCHOR_WAVENUMBERS,
    radius: int = NEIGHBORHOOD_RADIUS,
    stride: int = DOWNSAMPLE_STRIDE,
) -> CompressionResult:
    """Compress one spectrum file and publish the output atomically."""

    source = Path(source_path)
    output_dir = Path(output_directory)
    with source.open("r", encoding="utf-8-sig") as stream:
        points, skipped_lines = parse_spectrum_lines(stream)

    indexes = select_indexes(points, anchors=anchors, radius=radius, stride=stride)
    encoded_lines = [encode_intensity(points[index].intensity) for index in indexes]
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / source.name

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_dir,
            prefix=f".{source.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write("\n".join(encoded_lines))
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, output_path)
    except Exception:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise

    return CompressionResult(
        source_path=source,
        output_path=output_path,
        input_points=len(points),
        kept_points=len(indexes),
        skipped_lines=tuple(skipped_lines),
    )
