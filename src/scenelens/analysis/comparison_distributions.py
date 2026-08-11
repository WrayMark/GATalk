from __future__ import annotations

import cv2
import numpy as np

from scenelens.analysis.luminance import display_luminance
from scenelens.analysis.models import DistributionComparison, UInt8Image
from scenelens.analysis.palette import rgb_to_oklab


SUPPORTED_DISTRIBUTIONS = (
    "relative_luminance",
    "oklab_lightness",
    "oklab_chroma",
    "oklab_hue",
    "hsv_saturation",
)


def compare_colour_distribution(
    reference_rgb: UInt8Image,
    current_rgb: UInt8Image,
    *,
    metric: str = "relative_luminance",
    bins: int = 32,
    neutral_threshold: float = 0.04,
    max_sample_pixels: int = 240_000,
) -> DistributionComparison:
    """Return normalized, directly comparable image distributions.

    Sampling is spatially uniform and bounded so the result is deterministic
    and suitable for 4K source images. Hue excludes low-chroma pixels and
    reports that excluded share instead of inventing hue for neutral pixels.
    """
    if metric not in SUPPORTED_DISTRIBUTIONS:
        raise ValueError(f"unsupported comparison metric: {metric}")
    if bins not in {16, 32, 64, 128}:
        raise ValueError("bins must be one of 16, 32, 64 or 128")
    if not 0.0 <= neutral_threshold <= 0.25:
        raise ValueError("neutral_threshold must be inside 0..0.25")
    if max_sample_pixels < 1:
        raise ValueError("max_sample_pixels must be positive")

    reference_values, reference_excluded, value_range = _metric_values(
        _bounded_sample(reference_rgb, max_sample_pixels),
        metric,
        neutral_threshold,
    )
    current_values, current_excluded, current_range = _metric_values(
        _bounded_sample(current_rgb, max_sample_pixels),
        metric,
        neutral_threshold,
    )
    if current_range != value_range:
        raise RuntimeError("comparison distributions use inconsistent ranges")
    return DistributionComparison(
        metric=metric,
        reference_values=_normalized_histogram(
            reference_values, bins, value_range
        ),
        current_values=_normalized_histogram(
            current_values, bins, value_range
        ),
        range_min=value_range[0],
        range_max=value_range[1],
        reference_excluded_ratio=reference_excluded,
        current_excluded_ratio=current_excluded,
    )


def _bounded_sample(rgb: UInt8Image, maximum: int) -> UInt8Image:
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb image must have shape H x W x 3")
    height, width = rgb.shape[:2]
    if height * width <= maximum:
        return rgb
    scale = (maximum / float(height * width)) ** 0.5
    target = (max(1, int(width * scale)), max(1, int(height * scale)))
    return np.ascontiguousarray(
        cv2.resize(rgb, target, interpolation=cv2.INTER_AREA)
    )


def _metric_values(
    rgb: UInt8Image,
    metric: str,
    neutral_threshold: float,
) -> tuple[np.ndarray, float, tuple[float, float]]:
    if metric == "relative_luminance":
        return display_luminance(rgb).reshape(-1), 0.0, (0.0, 1.0)

    pixels = rgb.reshape(-1, 3).astype(np.float64) / 255.0
    if metric == "hsv_saturation":
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        return hsv[..., 1].reshape(-1).astype(np.float64) / 255.0, 0.0, (0.0, 1.0)

    oklab = rgb_to_oklab(pixels)
    if metric == "oklab_lightness":
        return np.clip(oklab[:, 0], 0.0, 1.0), 0.0, (0.0, 1.0)
    chroma = np.hypot(oklab[:, 1], oklab[:, 2])
    if metric == "oklab_chroma":
        # 0.4 covers normal display-referred sRGB while keeping bins stable
        # across both inputs. Outliers are accumulated in the final bin.
        return np.clip(chroma, 0.0, 0.4), 0.0, (0.0, 0.4)
    keep = chroma >= neutral_threshold
    excluded = 1.0 - float(np.count_nonzero(keep)) / float(chroma.size)
    hue = np.mod(np.degrees(np.arctan2(oklab[keep, 2], oklab[keep, 1])), 360.0)
    return hue, excluded, (0.0, 360.0)


def _normalized_histogram(
    values: np.ndarray,
    bins: int,
    value_range: tuple[float, float],
) -> tuple[float, ...]:
    if values.size == 0:
        return tuple(0.0 for _ in range(bins))
    counts, _ = np.histogram(values, bins=bins, range=value_range)
    total = int(counts.sum())
    if total == 0:
        return tuple(0.0 for _ in range(bins))
    return tuple(float(value) / total for value in counts)
