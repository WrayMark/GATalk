from __future__ import annotations

import cv2
import numpy as np
from numpy.typing import NDArray

from scenelens.analysis.models import (
    SharedPaletteColour,
    SharedPaletteResult,
    UInt8Image,
)
from scenelens.analysis.palette import (
    DEFAULT_MAX_SAMPLE_PIXELS,
    DEFAULT_RANDOM_SEED,
    extract_oklab_palette,
    rgb_to_oklab,
)


def extract_shared_oklab_palette(
    reference_rgb: UInt8Image,
    current_rgb: UInt8Image,
    colour_count: int = 8,
    max_samples_per_image: int = DEFAULT_MAX_SAMPLE_PIXELS,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> SharedPaletteResult:
    if colour_count < 1:
        raise ValueError("colour_count must be positive")
    if max_samples_per_image < colour_count:
        raise ValueError("max_samples_per_image must be at least colour_count")
    reference_samples = _equal_bounded_samples(
        reference_rgb,
        max_samples_per_image,
    )
    current_samples = _equal_bounded_samples(
        current_rgb,
        max_samples_per_image,
    )
    sample_count = min(len(reference_samples), len(current_samples))
    if sample_count == 0:
        return SharedPaletteResult((), 0, 0)
    reference_samples = _evenly_select(reference_samples, sample_count)
    current_samples = _evenly_select(current_samples, sample_count)
    combined = np.concatenate(
        (reference_samples, current_samples),
        axis=0,
    ).reshape(-1, 1, 3)
    palette, _ = extract_oklab_palette(
        combined,
        colour_count=colour_count,
        max_sample_pixels=sample_count * 2,
        random_seed=random_seed,
    )
    centres = np.asarray([item.oklab for item in palette], dtype=np.float64)
    reference_labels = classify_oklab_centres(reference_samples, centres)
    current_labels = classify_oklab_centres(current_samples, centres)
    reference_counts = np.bincount(
        reference_labels,
        minlength=len(palette),
    )
    current_counts = np.bincount(
        current_labels,
        minlength=len(palette),
    )
    colours = tuple(
        SharedPaletteColour(
            rgb=item.rgb,
            oklab=item.oklab,
            reference_proportion=float(reference_counts[index] / sample_count),
            current_proportion=float(current_counts[index] / sample_count),
        )
        for index, item in enumerate(palette)
    )
    return SharedPaletteResult(colours, sample_count, sample_count)


def palette_membership_mask(
    rgb: UInt8Image,
    centres_oklab: NDArray[np.floating],
    selected_index: int,
    chunk_rows: int = 128,
) -> NDArray[np.bool_]:
    centres = np.asarray(centres_oklab, dtype=np.float64)
    if centres.ndim != 2 or centres.shape[1] != 3:
        raise ValueError("centres_oklab must have shape (n, 3)")
    if not 0 <= selected_index < len(centres):
        raise ValueError("selected_index is outside the palette")
    height, width = rgb.shape[:2]
    output = np.empty((height, width), dtype=bool)
    for start in range(0, height, max(1, int(chunk_rows))):
        end = min(height, start + max(1, int(chunk_rows)))
        pixels = rgb[start:end].reshape(-1, 3)
        labels = classify_oklab_centres(pixels, centres)
        output[start:end] = labels.reshape(end - start, width) == selected_index
    return output


def render_palette_source_mask(
    rgb: UInt8Image,
    mask: NDArray[np.bool_],
) -> UInt8Image:
    if mask.shape != rgb.shape[:2]:
        raise ValueError("mask shape must match image height and width")
    output = np.rint(rgb.astype(np.float32) * 0.18).astype(np.uint8)
    output[mask] = rgb[mask]
    return np.ascontiguousarray(output)


def classify_oklab_centres(
    rgb_pixels: NDArray[np.uint8],
    centres_oklab: NDArray[np.floating],
) -> NDArray[np.int32]:
    pixels = np.asarray(rgb_pixels, dtype=np.uint8).reshape(-1, 3)
    centres = np.asarray(centres_oklab, dtype=np.float64)
    if len(pixels) == 0:
        return np.empty(0, dtype=np.int32)
    pixels_oklab = rgb_to_oklab(
        pixels.astype(np.float64) / 255.0
    ).astype(np.float32)
    distances = (
        pixels_oklab[:, np.newaxis, :]
        - centres.astype(np.float32)[np.newaxis, :, :]
    )
    return np.argmin(
        np.einsum("nki,nki->nk", distances, distances),
        axis=1,
    ).astype(np.int32)


def _equal_bounded_samples(
    rgb: UInt8Image,
    maximum: int,
) -> NDArray[np.uint8]:
    height, width = rgb.shape[:2]
    if height * width <= maximum:
        return np.ascontiguousarray(rgb.reshape(-1, 3))
    scale = (maximum / float(height * width)) ** 0.5
    sampled_width = max(1, int(width * scale))
    sampled_height = max(1, int(height * scale))
    sampled = cv2.resize(
        rgb,
        (sampled_width, sampled_height),
        interpolation=cv2.INTER_AREA,
    )
    return np.ascontiguousarray(sampled.reshape(-1, 3))


def _evenly_select(
    samples: NDArray[np.uint8],
    count: int,
) -> NDArray[np.uint8]:
    if len(samples) == count:
        return samples
    indices = np.linspace(0, len(samples) - 1, count, dtype=np.int64)
    return np.ascontiguousarray(samples[indices])
