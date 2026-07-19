from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from scenelens.analysis.luminance import (
    display_luminance,
    relative_luminance,
)
from scenelens.analysis.models import UInt8Image
from scenelens.analysis.palette import rgb_to_oklab
from scenelens.analysis.shared_palette import classify_oklab_centres


DEFAULT_NEUTRAL_CHROMA_THRESHOLD = 0.03
DEFAULT_HUE_BINS = 12
DEFAULT_MAX_REGION_COLOUR_SAMPLES = 250_000


@dataclass(frozen=True)
class RegionStatistics:
    pixel_count: int
    colour_sample_count: int
    mean_linear_luminance: float
    mean_oklab_l: float
    luminance_standard_deviation: float
    luminance_p10: float
    luminance_p50: float
    luminance_p90: float
    effective_luminance_span: float
    three_value_ratios: tuple[float, float, float]
    mean_oklab: tuple[float, float, float]
    mean_chroma: float
    median_chroma: float
    neutral_ratio: float
    chromatic_pixel_count: int
    hue_mean_degrees: float | None
    hue_distribution: tuple[float, ...]
    shared_palette_proportions: tuple[float, ...]


@dataclass(frozen=True)
class PairedRegionAnalysis:
    reference: RegionStatistics
    current: RegionStatistics
    low_threshold: float
    high_threshold: float
    neutral_chroma_threshold: float
    hue_bins: int
    max_colour_samples: int


def analyze_paired_regions(
    reference_rgb: UInt8Image,
    current_rgb: UInt8Image,
    reference_rect: tuple[float, float, float, float],
    current_rect: tuple[float, float, float, float],
    shared_palette_centres: NDArray[np.floating],
    *,
    low_threshold: float = 1.0 / 3.0,
    high_threshold: float = 2.0 / 3.0,
    neutral_chroma_threshold: float = DEFAULT_NEUTRAL_CHROMA_THRESHOLD,
    hue_bins: int = DEFAULT_HUE_BINS,
    max_colour_samples: int = DEFAULT_MAX_REGION_COLOUR_SAMPLES,
) -> PairedRegionAnalysis:
    _validate_parameters(
        low_threshold,
        high_threshold,
        neutral_chroma_threshold,
        hue_bins,
        max_colour_samples,
    )
    centres = np.asarray(shared_palette_centres, dtype=np.float64)
    if centres.ndim != 2 or centres.shape[1] != 3 or len(centres) < 1:
        raise ValueError("shared_palette_centres must have shape (n, 3)")
    return PairedRegionAnalysis(
        reference=analyze_region(
            reference_rgb,
            reference_rect,
            centres,
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            neutral_chroma_threshold=neutral_chroma_threshold,
            hue_bins=hue_bins,
            max_colour_samples=max_colour_samples,
        ),
        current=analyze_region(
            current_rgb,
            current_rect,
            centres,
            low_threshold=low_threshold,
            high_threshold=high_threshold,
            neutral_chroma_threshold=neutral_chroma_threshold,
            hue_bins=hue_bins,
            max_colour_samples=max_colour_samples,
        ),
        low_threshold=float(low_threshold),
        high_threshold=float(high_threshold),
        neutral_chroma_threshold=float(neutral_chroma_threshold),
        hue_bins=int(hue_bins),
        max_colour_samples=int(max_colour_samples),
    )


def analyze_region(
    rgb: UInt8Image,
    normalized_rect: tuple[float, float, float, float],
    shared_palette_centres: NDArray[np.floating],
    *,
    low_threshold: float = 1.0 / 3.0,
    high_threshold: float = 2.0 / 3.0,
    neutral_chroma_threshold: float = DEFAULT_NEUTRAL_CHROMA_THRESHOLD,
    hue_bins: int = DEFAULT_HUE_BINS,
    max_colour_samples: int = DEFAULT_MAX_REGION_COLOUR_SAMPLES,
) -> RegionStatistics:
    _validate_rgb(rgb)
    _validate_parameters(
        low_threshold,
        high_threshold,
        neutral_chroma_threshold,
        hue_bins,
        max_colour_samples,
    )
    crop = crop_normalized_region(rgb, normalized_rect)
    linear_values = relative_luminance(crop).reshape(-1)
    display_values = display_luminance(crop).reshape(-1)
    p10, p50, p90 = np.percentile(linear_values, (10.0, 50.0, 90.0))
    total = float(len(display_values))
    three_ratios = (
        float(np.count_nonzero(display_values < low_threshold) / total),
        float(
            np.count_nonzero(
                (display_values >= low_threshold)
                & (display_values < high_threshold)
            )
            / total
        ),
        float(np.count_nonzero(display_values >= high_threshold) / total),
    )

    colour_pixels = bounded_region_colour_sample(crop, max_colour_samples)
    oklab = rgb_to_oklab(
        colour_pixels.astype(np.float64) / 255.0
    )
    mean_oklab_array = np.mean(oklab, axis=0)
    chroma = np.hypot(oklab[:, 1], oklab[:, 2])
    neutral = chroma < neutral_chroma_threshold
    chromatic = ~neutral
    chromatic_count = int(np.count_nonzero(chromatic))
    hue_distribution = np.zeros(hue_bins, dtype=np.float64)
    hue_mean: float | None = None
    if chromatic_count:
        hue_radians = np.mod(
            np.arctan2(oklab[chromatic, 2], oklab[chromatic, 1]),
            2.0 * np.pi,
        )
        hue_indices = np.minimum(
            hue_bins - 1,
            np.floor(hue_radians / (2.0 * np.pi) * hue_bins).astype(
                np.int32
            ),
        )
        hue_distribution = (
            np.bincount(hue_indices, minlength=hue_bins).astype(np.float64)
            / chromatic_count
        )
        weights = chroma[chromatic]
        sine = float(np.sum(np.sin(hue_radians) * weights))
        cosine = float(np.sum(np.cos(hue_radians) * weights))
        if abs(sine) > 1e-12 or abs(cosine) > 1e-12:
            hue_mean = float(np.degrees(np.mod(np.arctan2(sine, cosine), 2.0 * np.pi)))

    centres = np.asarray(shared_palette_centres, dtype=np.float64)
    labels = classify_oklab_centres(colour_pixels, centres)
    palette_counts = np.bincount(labels, minlength=len(centres))
    palette_proportions = palette_counts.astype(np.float64) / float(
        len(labels)
    )
    return RegionStatistics(
        pixel_count=int(crop.shape[0] * crop.shape[1]),
        colour_sample_count=int(len(colour_pixels)),
        mean_linear_luminance=float(np.mean(linear_values)),
        mean_oklab_l=float(mean_oklab_array[0]),
        luminance_standard_deviation=float(np.std(linear_values)),
        luminance_p10=float(p10),
        luminance_p50=float(p50),
        luminance_p90=float(p90),
        effective_luminance_span=float(p90 - p10),
        three_value_ratios=three_ratios,
        mean_oklab=tuple(float(value) for value in mean_oklab_array),
        mean_chroma=float(np.mean(chroma)),
        median_chroma=float(np.median(chroma)),
        neutral_ratio=float(np.count_nonzero(neutral) / len(neutral)),
        chromatic_pixel_count=chromatic_count,
        hue_mean_degrees=hue_mean,
        hue_distribution=tuple(
            float(value) for value in hue_distribution
        ),
        shared_palette_proportions=tuple(
            float(value) for value in palette_proportions
        ),
    )


def crop_normalized_region(
    rgb: UInt8Image,
    normalized_rect: tuple[float, float, float, float],
) -> UInt8Image:
    _validate_rgb(rgb)
    x, y, width, height = (float(value) for value in normalized_rect)
    if (
        x < 0.0
        or y < 0.0
        or width <= 0.0
        or height <= 0.0
        or x + width > 1.0 + 1e-9
        or y + height > 1.0 + 1e-9
    ):
        raise ValueError("normalized_rect must be a non-empty rectangle in 0..1")
    image_height, image_width = rgb.shape[:2]
    left = max(0, min(image_width - 1, int(np.floor(x * image_width))))
    top = max(0, min(image_height - 1, int(np.floor(y * image_height))))
    right = max(left + 1, min(image_width, int(np.ceil((x + width) * image_width))))
    bottom = max(
        top + 1,
        min(image_height, int(np.ceil((y + height) * image_height))),
    )
    return np.ascontiguousarray(rgb[top:bottom, left:right])


def bounded_region_colour_sample(
    crop: UInt8Image,
    maximum: int,
) -> NDArray[np.uint8]:
    height, width = crop.shape[:2]
    if height * width <= maximum:
        return np.ascontiguousarray(crop.reshape(-1, 3))
    scale = (maximum / float(height * width)) ** 0.5
    sampled_width = max(1, int(width * scale))
    sampled_height = max(1, int(height * scale))
    sampled = cv2.resize(
        crop,
        (sampled_width, sampled_height),
        interpolation=cv2.INTER_AREA,
    )
    return np.ascontiguousarray(sampled.reshape(-1, 3))


def render_region_palette_source_mask(
    rgb: UInt8Image,
    normalized_rect: tuple[float, float, float, float],
    centres_oklab: NDArray[np.floating],
    selected_index: int,
) -> UInt8Image:
    _validate_rgb(rgb)
    crop = crop_normalized_region(rgb, normalized_rect)
    centres = np.asarray(centres_oklab, dtype=np.float64)
    if not 0 <= selected_index < len(centres):
        raise ValueError("selected_index is outside the palette")
    labels = classify_oklab_centres(crop.reshape(-1, 3), centres).reshape(
        crop.shape[:2]
    )
    selected = labels == selected_index
    output = np.rint(rgb.astype(np.float32) * 0.08).astype(np.uint8)
    x, y, width, height = normalized_rect
    image_height, image_width = rgb.shape[:2]
    left = max(0, min(image_width - 1, int(np.floor(x * image_width))))
    top = max(0, min(image_height - 1, int(np.floor(y * image_height))))
    right = min(image_width, left + crop.shape[1])
    bottom = min(image_height, top + crop.shape[0])
    region_output = np.rint(crop.astype(np.float32) * 0.18).astype(np.uint8)
    region_output[selected] = crop[selected]
    output[top:bottom, left:right] = region_output[: bottom - top, : right - left]
    return np.ascontiguousarray(output)


def _validate_rgb(rgb: UInt8Image) -> None:
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
        raise ValueError("rgb must be uint8 with shape (height, width, 3)")
    if rgb.shape[0] < 1 or rgb.shape[1] < 1:
        raise ValueError("rgb must not be empty")


def _validate_parameters(
    low_threshold: float,
    high_threshold: float,
    neutral_chroma_threshold: float,
    hue_bins: int,
    max_colour_samples: int,
) -> None:
    if not 0.0 < low_threshold < high_threshold < 1.0:
        raise ValueError("thresholds must satisfy 0 < low < high < 1")
    if neutral_chroma_threshold < 0.0:
        raise ValueError("neutral_chroma_threshold must not be negative")
    if hue_bins < 3:
        raise ValueError("hue_bins must be at least 3")
    if max_colour_samples < 1:
        raise ValueError("max_colour_samples must be positive")
