from __future__ import annotations

import numpy as np

from scenelens.analysis.luminance import (
    gaussian_blur,
    grayscale_rgb,
    luminance_histogram,
    quantize_luminance,
)
from scenelens.analysis.models import ImageMeasurements, RenderSettings, UInt8Image
from scenelens.analysis.palette import extract_oklab_palette


def measure_image(
    rgb: UInt8Image,
    alpha: UInt8Image | None = None,
    palette_colours: int = 8,
) -> ImageMeasurements:
    mask = None if alpha is None else alpha > 0
    palette, sampled_pixel_count = extract_oklab_palette(
        rgb,
        colour_count=palette_colours,
        mask=mask,
    )
    histogram = luminance_histogram(rgb, mask=mask)
    return ImageMeasurements(
        luminance_histogram=histogram,
        palette=palette,
        sampled_pixel_count=sampled_pixel_count,
    )


def render_image(rgb: UInt8Image, settings: RenderSettings) -> UInt8Image:
    working = gaussian_blur(rgb, settings.blur_sigma)
    if settings.mode == "original":
        result = working
    elif settings.mode == "grayscale":
        result = grayscale_rgb(working)
    elif settings.mode == "three_value":
        result = quantize_luminance(working, 3)
    elif settings.mode == "five_value":
        result = quantize_luminance(working, 5)
    else:
        raise ValueError(f"Unsupported render mode: {settings.mode}")
    return np.ascontiguousarray(result)

