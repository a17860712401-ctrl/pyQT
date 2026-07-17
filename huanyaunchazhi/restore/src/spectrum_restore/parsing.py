from __future__ import annotations

import math
import re
from pathlib import Path

from .models import TemplateAxis


_TEMPLATE_SPLIT = re.compile(r"[,，\s]+")
_HEX_INTENSITY = re.compile(r"[0-9A-Fa-f]+")


class SpectrumFormatError(ValueError):
    """Raised when an input spectrum file violates its format contract."""


def _read_lines(path: Path | str) -> list[str]:
    source = Path(path)
    try:
        return source.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeError as error:
        raise SpectrumFormatError(f"文件 {source.name} 不是有效的 UTF-8 文本") from error
    except OSError as error:
        raise SpectrumFormatError(f"无法读取文件 {source.name}：{error}") from error


def parse_template(path: Path | str) -> TemplateAxis:
    raw_values: list[str] = []
    values: list[float] = []
    seen: set[float] = set()

    for line_number, raw_line in enumerate(_read_lines(path), start=1):
        line = raw_line.strip()
        if not line:
            continue
        token = _TEMPLATE_SPLIT.split(line, maxsplit=1)[0]
        try:
            value = float(token)
        except ValueError as error:
            raise SpectrumFormatError(f"模板第 {line_number} 行第一列不是数值") from error
        if not math.isfinite(value):
            raise SpectrumFormatError(f"模板第 {line_number} 行横坐标必须是有限数值")
        if value in seen:
            raise SpectrumFormatError(f"模板第 {line_number} 行横坐标重复：{token}")
        seen.add(value)
        raw_values.append(token)
        values.append(value)

    if not values:
        raise SpectrumFormatError("横坐标模板为空")
    if len(values) > 1:
        increasing = all(left < right for left, right in zip(values, values[1:]))
        decreasing = all(left > right for left, right in zip(values, values[1:]))
        if not increasing and not decreasing:
            raise SpectrumFormatError("模板横坐标必须严格递增或严格递减")
    return TemplateAxis(tuple(raw_values), tuple(values))


def parse_compressed(path: Path | str) -> tuple[int, ...]:
    values: list[int] = []

    for line_number, raw_line in enumerate(_read_lines(path), start=1):
        token = raw_line.strip()
        if not token:
            continue
        if len(token) not in (2, 4, 6, 8) or _HEX_INTENSITY.fullmatch(token) is None:
            raise SpectrumFormatError(
                f"压缩文件第 {line_number} 行不是 2、4、6 或 8 位十六进制强度"
            )
        values.append(int(token, 16))

    if not values:
        raise SpectrumFormatError("压缩文件为空")
    return tuple(values)
