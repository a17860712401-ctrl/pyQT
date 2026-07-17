from __future__ import annotations

from collections.abc import Sequence


ANCHOR_WAVENUMBERS = (981.0, 1386.0, 2911.0, 2578.0, 2593.0, 4134.0)
NEIGHBORHOOD_RADIUS = 9
DOWNSAMPLE_STRIDE = 35


def select_indexes(
    wavenumbers: Sequence[float],
    *,
    anchors: Sequence[float] = ANCHOR_WAVENUMBERS,
    radius: int = NEIGHBORHOOD_RADIUS,
    stride: int = DOWNSAMPLE_STRIDE,
) -> tuple[int, ...]:
    """Return the indexes retained by the companion compressor."""

    if not wavenumbers:
        return ()
    if radius < 0:
        raise ValueError("邻域半径不能小于 0")
    if stride <= 0:
        raise ValueError("降采样步长必须大于 0")

    selected = set(range(0, len(wavenumbers), stride))
    selected.update((0, len(wavenumbers) - 1))
    minimum = min(wavenumbers)
    maximum = max(wavenumbers)

    for anchor in anchors:
        if not minimum <= anchor <= maximum:
            continue
        center = min(
            range(len(wavenumbers)),
            key=lambda index: (abs(wavenumbers[index] - anchor), index),
        )
        start = max(0, center - radius)
        stop = min(len(wavenumbers), center + radius + 1)
        selected.update(range(start, stop))

    return tuple(sorted(selected))
