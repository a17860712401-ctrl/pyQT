from __future__ import annotations

import bisect
import math
from collections.abc import Sequence


class InterpolationError(ValueError):
    """Raised when interpolation inputs are invalid or require extrapolation."""


def _validate_known(
    known_x: Sequence[float], known_y: Sequence[float], *, minimum: int
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    x = tuple(float(value) for value in known_x)
    y = tuple(float(value) for value in known_y)
    if len(x) != len(y) or len(x) < minimum:
        raise InterpolationError("已知横坐标与强度数量不匹配或数量不足")
    if any(not math.isfinite(value) for value in (*x, *y)):
        raise InterpolationError("插值数据必须是有限数值")
    if any(left >= right for left, right in zip(x, x[1:])):
        raise InterpolationError("已知横坐标必须严格递增")
    return x, y


def _validate_queries(query_x: Sequence[float], lower: float, upper: float) -> tuple[float, ...]:
    queries = tuple(float(value) for value in query_x)
    if any(not math.isfinite(value) for value in queries):
        raise InterpolationError("待插值横坐标必须是有限数值")
    if any(value < lower or value > upper for value in queries):
        raise InterpolationError("待插值横坐标超出真实点范围，禁止外推")
    return queries


def _endpoint_slope(h0: float, h1: float, delta0: float, delta1: float) -> float:
    slope = ((2.0 * h0 + h1) * delta0 - h0 * delta1) / (h0 + h1)
    if slope * delta0 <= 0.0:
        return 0.0
    if delta0 * delta1 < 0.0 and abs(slope) > abs(3.0 * delta0):
        return 3.0 * delta0
    return slope


def _pchip_slopes(x: tuple[float, ...], y: tuple[float, ...]) -> tuple[float, ...]:
    if len(x) == 2:
        slope = (y[1] - y[0]) / (x[1] - x[0])
        return (slope, slope)

    h = tuple(right - left for left, right in zip(x, x[1:]))
    delta = tuple((y[index + 1] - y[index]) / h[index] for index in range(len(h)))
    slopes = [0.0] * len(x)
    slopes[0] = _endpoint_slope(h[0], h[1], delta[0], delta[1])
    slopes[-1] = _endpoint_slope(h[-1], h[-2], delta[-1], delta[-2])

    for index in range(1, len(x) - 1):
        left_delta = delta[index - 1]
        right_delta = delta[index]
        if left_delta * right_delta <= 0.0:
            slopes[index] = 0.0
            continue
        left_h = h[index - 1]
        right_h = h[index]
        weight1 = 2.0 * right_h + left_h
        weight2 = right_h + 2.0 * left_h
        slopes[index] = (weight1 + weight2) / (
            weight1 / left_delta + weight2 / right_delta
        )
    return tuple(slopes)


def pchip_interpolate(
    known_x: Sequence[float],
    known_y: Sequence[float],
    query_x: Sequence[float],
) -> tuple[float, ...]:
    """Evaluate shape-preserving cubic Hermite segments without extrapolation."""

    x, y = _validate_known(known_x, known_y, minimum=2)
    queries = _validate_queries(query_x, x[0], x[-1])
    slopes = _pchip_slopes(x, y)
    results: list[float] = []

    for query in queries:
        interval = min(max(bisect.bisect_right(x, query) - 1, 0), len(x) - 2)
        width = x[interval + 1] - x[interval]
        t = (query - x[interval]) / width
        t2 = t * t
        t3 = t2 * t
        value = (
            (2.0 * t3 - 3.0 * t2 + 1.0) * y[interval]
            + (t3 - 2.0 * t2 + t) * width * slopes[interval]
            + (-2.0 * t3 + 3.0 * t2) * y[interval + 1]
            + (t3 - t2) * width * slopes[interval + 1]
        )
        if not math.isfinite(value):
            raise InterpolationError("PCHIP 产生了非有限强度")
        results.append(value)
    return tuple(results)


def linear_interpolate(
    known_x: Sequence[float],
    known_y: Sequence[float],
    query_x: Sequence[float],
) -> tuple[float, ...]:
    """Evaluate piecewise linear segments without extrapolation."""

    x, y = _validate_known(known_x, known_y, minimum=2)
    queries = _validate_queries(query_x, x[0], x[-1])
    results: list[float] = []
    for query in queries:
        interval = min(max(bisect.bisect_right(x, query) - 1, 0), len(x) - 2)
        ratio = (query - x[interval]) / (x[interval + 1] - x[interval])
        results.append(y[interval] + ratio * (y[interval + 1] - y[interval]))
    return tuple(results)


def interpolate_with_fallback(
    known_x: Sequence[float],
    known_y: Sequence[float],
    query_x: Sequence[float],
) -> tuple[tuple[float, ...], str, tuple[str, ...]]:
    if len(known_x) == 1:
        x = float(known_x[0])
        y = float(known_y[0])
        queries = _validate_queries(query_x, x, x)
        return tuple(y for _ in queries), "无需插值", ()
    if len(known_x) == 2:
        return linear_interpolate(known_x, known_y, query_x), "线性插值", ()
    try:
        return pchip_interpolate(known_x, known_y, query_x), "PCHIP", ()
    except (ArithmeticError, InterpolationError, OverflowError, ValueError) as error:
        warning = f"PCHIP 失败，已改用线性插值：{error}"
        values = linear_interpolate(known_x, known_y, query_x)
        return values, "线性插值", (warning,)
