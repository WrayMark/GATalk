from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from scenelens.analysis.models import UInt8Image


def srgb_to_linear(values: NDArray[np.floating]) -> NDArray[np.float32]:
    """Decode gamma-encoded sRGB values in the 0..1 range."""
    values_f = np.asarray(values, dtype=np.float32)
    return np.where(
        values_f <= 0.04045,
        values_f / 12.92,
        ((values_f + 0.055) / 1.055) ** 2.4,
    ).astype(np.float32, copy=False)


def linear_to_srgb(values: NDArray[np.floating]) -> NDArray[np.float32]:
    """Encode linear RGB/luminance values into display-referred sRGB."""
    values_f = np.clip(np.asarray(values, dtype=np.float32), 0.0, 1.0)
    return np.where(
        values_f <= 0.0031308,
        values_f * 12.92,
        1.055 * np.power(values_f, 1.0 / 2.4) - 0.055,
    ).astype(np.float32, copy=False)


def relative_luminance(rgb: UInt8Image) -> NDArray[np.float32]:
    """Return linear-light Rec.709/sRGB relative luminance."""
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must have shape (height, width, 3)")
    linear = srgb_to_linear(rgb.astype(np.float32) / 255.0)
    return (
        linear[..., 0] * 0.2126
        + linear[..., 1] * 0.7152
        + linear[..., 2] * 0.0722
    ).astype(np.float32, copy=False)


def display_luminance(rgb: UInt8Image) -> NDArray[np.float32]:
    """Return perceptually displayable luminance in the 0..1 range."""
    return linear_to_srgb(relative_luminance(rgb))


def luminance_histogram(
    rgb: UInt8Image,
    mask: NDArray[np.bool_] | None = None,
    bins: int = 256,
) -> NDArray[np.float64]:
    values = display_luminance(rgb)
    if mask is not None:
        if mask.shape != values.shape:
            raise ValueError("mask shape must match image height and width")
        values = values[mask]
    else:
        values = values.reshape(-1)

    if values.size == 0:
        return np.zeros(bins, dtype=np.float64)

    counts, _ = np.histogram(values, bins=bins, range=(0.0, 1.0))
    return counts.astype(np.float64) / float(counts.sum())


def gaussian_blur(rgb: UInt8Image, sigma: float) -> UInt8Image:
    if sigma <= 0.0:
        return np.ascontiguousarray(rgb)
    kernel = max(3, int(round(sigma * 6.0)) | 1)
    kernel = min(kernel, 151)
    return cv2.GaussianBlur(
        rgb,
        (kernel, kernel),
        sigmaX=float(sigma),
        sigmaY=float(sigma),
        borderType=cv2.BORDER_REFLECT101,
    )


def grayscale_rgb(rgb: UInt8Image) -> UInt8Image:
    gray = np.rint(display_luminance(rgb) * 255.0).astype(np.uint8)
    return np.repeat(gray[..., np.newaxis], 3, axis=2)


def quantize_luminance(rgb: UInt8Image, levels: int) -> UInt8Image:
    if levels not in (3, 5):
        raise ValueError("levels must be 3 or 5")

    thresholds = np.linspace(0.0, 1.0, levels + 1, dtype=np.float32)[1:-1]
    return quantize_luminance_with_thresholds(
        rgb,
        tuple(float(value) for value in thresholds),
    )


def three_value_ratios(
    rgb: UInt8Image,
    low_threshold: float = 1.0 / 3.0,
    high_threshold: float = 2.0 / 3.0,
    mask: NDArray[np.bool_] | None = None,
) -> tuple[float, float, float]:
    if not 0.0 < low_threshold < high_threshold < 1.0:
        raise ValueError("thresholds must satisfy 0 < low < high < 1")
    values = display_luminance(rgb)
    if mask is not None:
        if mask.shape != values.shape:
            raise ValueError("mask shape must match image height and width")
        values = values[mask]
    else:
        values = values.reshape(-1)
    if values.size == 0:
        return (0.0, 0.0, 0.0)
    total = float(values.size)
    dark = float(np.count_nonzero(values < low_threshold) / total)
    middle = float(
        np.count_nonzero(
            (values >= low_threshold) & (values < high_threshold)
        )
        / total
    )
    bright = float(np.count_nonzero(values >= high_threshold) / total)
    return dark, middle, bright


def quantize_three_value_with_thresholds(
    rgb: UInt8Image,
    low_threshold: float,
    high_threshold: float,
) -> UInt8Image:
    ratios_check = (float(low_threshold), float(high_threshold))
    if not 0.0 < ratios_check[0] < ratios_check[1] < 1.0:
        raise ValueError("thresholds must satisfy 0 < low < high < 1")
    return quantize_luminance_with_thresholds(rgb, ratios_check)


def quantize_luminance_with_thresholds(
    rgb: UInt8Image,
    thresholds: tuple[float, ...],
) -> UInt8Image:
    edges = np.asarray(thresholds, dtype=np.float32)
    if (
        len(edges) == 0
        or np.any(edges <= 0.0)
        or np.any(edges >= 1.0)
        or np.any(np.diff(edges) <= 0.0)
    ):
        raise ValueError("thresholds must be strictly increasing inside 0..1")
    indices = np.digitize(display_luminance(rgb), edges, right=False)
    output_values = np.linspace(
        0,
        255,
        len(edges) + 1,
        dtype=np.uint8,
    )
    quantized = output_values[indices]
    return np.repeat(quantized[..., np.newaxis], 3, axis=2)
