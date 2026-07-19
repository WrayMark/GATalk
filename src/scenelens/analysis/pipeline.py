from __future__ import annotations

import numpy as np

from scenelens.analysis.luminance import (
    gaussian_blur,
    grayscale_rgb,
    luminance_histogram,
    quantize_luminance_with_thresholds,
)
from scenelens.analysis.lighting import (
    clipping_warning,
    exposure_false_colour,
    lighting_luminance_proxy,
    luminance_blur,
    silhouette_map,
    thumbnail_observation,
)
from scenelens.analysis.models import ImageMeasurements, RenderSettings, UInt8Image
from scenelens.analysis.palette import extract_oklab_palette
from scenelens.analysis.palette import (
    DEFAULT_MAX_SAMPLE_PIXELS,
    DEFAULT_RANDOM_SEED,
)


def measure_image(
    rgb: UInt8Image,
    alpha: UInt8Image | None = None,
    palette_colours: int = 8,
    palette_seed: int = DEFAULT_RANDOM_SEED,
    palette_max_samples: int = DEFAULT_MAX_SAMPLE_PIXELS,
) -> ImageMeasurements:
    mask = None if alpha is None else alpha > 0
    palette, sampled_pixel_count = extract_oklab_palette(
        rgb,
        colour_count=palette_colours,
        mask=mask,
        max_sample_pixels=palette_max_samples,
        random_seed=palette_seed,
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
        result = quantize_luminance_with_thresholds(
            working,
            settings.three_thresholds,
        )
    elif settings.mode == "five_value":
        result = quantize_luminance_with_thresholds(
            working,
            settings.five_thresholds,
        )
    elif settings.mode == "exposure_false_colour":
        result = exposure_false_colour(working)
    elif settings.mode == "clipping_warning":
        result = clipping_warning(
            working,
            shadow_threshold=settings.clipping_shadow_threshold,
            highlight_threshold=settings.clipping_highlight_threshold,
        )
    elif settings.mode == "silhouette":
        result = silhouette_map(
            working,
            threshold=settings.silhouette_threshold,
        )
    elif settings.mode == "thumbnail_observation":
        result = thumbnail_observation(
            working,
            maximum_side=settings.thumbnail_maximum_side,
        )
    elif settings.mode == "luminance_blur":
        result = luminance_blur(
            rgb,
            sigma=max(1.0, settings.blur_sigma),
        )
    elif settings.mode == "lighting_luminance_proxy":
        result = lighting_luminance_proxy(
            rgb,
            sigma=max(1.0, settings.blur_sigma),
        )
    else:
        raise ValueError(f"Unsupported render mode: {settings.mode}")
    return np.ascontiguousarray(result)
