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

    luminance = display_luminance(rgb)
    thresholds = np.linspace(0.0, 1.0, levels + 1, dtype=np.float32)[1:-1]
    indices = np.digitize(luminance, thresholds, right=False)
    output_values = np.linspace(0, 255, levels, dtype=np.uint8)
    quantized = output_values[indices]
    return np.repeat(quantized[..., np.newaxis], 3, axis=2)

