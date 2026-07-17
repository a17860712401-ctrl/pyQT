from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_UP


def format_intensity(value: int | float) -> str:
    """Format a decimal intensity with no more than four decimal places."""

    if isinstance(value, int):
        return str(value)
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("还原强度必须是有限数值")
    rounded = Decimal(str(numeric)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if rounded == 0:
        return "0"
    return format(rounded, "f").rstrip("0").rstrip(".")
