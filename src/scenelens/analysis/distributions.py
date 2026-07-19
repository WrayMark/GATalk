from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from scenelens.analysis.luminance import display_luminance
from scenelens.analysis.models import UInt8Image


def value_band_ratios(
    rgb: UInt8Image,
    thresholds: tuple[float, ...],
    mask: NDArray[np.bool_] | None = None,
) -> tuple[float, ...]:
    edges = np.asarray(thresholds, dtype=np.float32)
    if (
        len(edges) == 0
        or np.any(edges <= 0.0)
        or np.any(edges >= 1.0)
        or np.any(np.diff(edges) <= 0.0)
    ):
        raise ValueError("thresholds must be strictly increasing inside 0..1")
    values = display_luminance(rgb)
    if mask is not None:
        if mask.shape != values.shape:
            raise ValueError("mask shape must match image height and width")
        values = values[mask]
    else:
        values = values.reshape(-1)
    if values.size == 0:
        return tuple(0.0 for _ in range(len(edges) + 1))
    counts = np.bincount(
        np.digitize(values, edges, right=False),
        minlength=len(edges) + 1,
    )
    return tuple(float(value / values.size) for value in counts)


def hue_saturation_distribution(
    rgb: UInt8Image,
    *,
    hue_bins: int = 12,
    saturation_bins: int = 10,
) -> dict[str, object]:
    if hue_bins < 1 or saturation_bins < 1:
        raise ValueError("histogram bin counts must be positive")
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue = hsv[..., 0].astype(np.float32) * 2.0
    saturation = hsv[..., 1].astype(np.float32) / 255.0
    chromatic = saturation >= 0.05
    if np.any(chromatic):
        hue_counts, _ = np.histogram(
            hue[chromatic],
            bins=hue_bins,
            range=(0.0, 360.0),
        )
        hue_values = (
            hue_counts.astype(np.float64) / float(hue_counts.sum())
        ).tolist()
    else:
        hue_values = [0.0] * hue_bins
    saturation_counts, _ = np.histogram(
        saturation,
        bins=saturation_bins,
        range=(0.0, 1.0),
    )
    saturation_values = (
        saturation_counts.astype(np.float64)
        / float(saturation_counts.sum())
    ).tolist()
    return {
        "hue_bins_degrees": hue_bins,
        "hue_proportions": hue_values,
        "saturation_bins": saturation_bins,
        "saturation_proportions": saturation_values,
        "mean_saturation": float(np.mean(saturation)),
    }
