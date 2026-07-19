from __future__ import annotations

import cv2
import numpy as np

from scenelens.analysis.luminance import (
    display_luminance,
    gaussian_blur,
    grayscale_rgb,
)
from scenelens.analysis.models import UInt8Image


def exposure_false_colour(rgb: UInt8Image) -> UInt8Image:
    """Return a display-luminance false-colour map, not a calibrated EV map."""

    values = display_luminance(rgb)
    edges = np.asarray(
        [0.04, 0.12, 0.28, 0.5, 0.72, 0.9],
        dtype=np.float32,
    )
    colours = np.asarray(
        [
            [18, 10, 35],
            [55, 35, 130],
            [20, 100, 210],
            [20, 175, 105],
            [235, 210, 35],
            [235, 80, 25],
            [255, 245, 240],
        ],
        dtype=np.uint8,
    )
    return np.ascontiguousarray(colours[np.digitize(values, edges)])


def clipping_warning(
    rgb: UInt8Image,
    *,
    shadow_threshold: float = 0.02,
    highlight_threshold: float = 0.98,
) -> UInt8Image:
    if not 0.0 <= shadow_threshold < highlight_threshold <= 1.0:
        raise ValueError("clipping thresholds must be ordered inside 0..1")
    values = display_luminance(rgb)
    output = np.rint(
        grayscale_rgb(rgb).astype(np.float32) * 0.45
    ).astype(np.uint8)
    output[values <= shadow_threshold] = (30, 90, 255)
    output[values >= highlight_threshold] = (255, 45, 35)
    return np.ascontiguousarray(output)


def silhouette_map(
    rgb: UInt8Image,
    *,
    threshold: float = 0.45,
) -> UInt8Image:
    if not 0.0 < threshold < 1.0:
        raise ValueError("silhouette threshold must be inside 0..1")
    values = np.where(display_luminance(rgb) >= threshold, 255, 0)
    gray = values.astype(np.uint8)
    return np.repeat(gray[..., None], 3, axis=2)


def thumbnail_observation(
    rgb: UInt8Image,
    *,
    maximum_side: int = 160,
) -> UInt8Image:
    if maximum_side < 8:
        raise ValueError("maximum_side must be at least 8")
    height, width = rgb.shape[:2]
    scale = min(1.0, maximum_side / float(max(height, width)))
    small = cv2.resize(
        rgb,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    return np.ascontiguousarray(
        cv2.resize(
            small,
            (width, height),
            interpolation=cv2.INTER_NEAREST,
        )
    )


def luminance_blur(
    rgb: UInt8Image,
    *,
    sigma: float = 8.0,
) -> UInt8Image:
    return grayscale_rgb(gaussian_blur(rgb, sigma))


def lighting_luminance_proxy(
    rgb: UInt8Image,
    *,
    sigma: float = 3.0,
) -> UInt8Image:
    """Reduce colour/detail interference without claiming material removal."""

    blurred = gaussian_blur(rgb, sigma)
    values = np.clip(display_luminance(blurred), 0.0, 1.0)
    # A gentle S-curve preserves broad lighting structure while suppressing
    # small material variations.
    shaped = values * values * (3.0 - 2.0 * values)
    gray = np.rint(shaped * 255.0).astype(np.uint8)
    return np.repeat(gray[..., None], 3, axis=2)
