from __future__ import annotations

import threading
import warnings

import cv2
import numpy as np
from numpy.typing import NDArray

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message='.*"SciPy".*not available.*')
    warnings.filterwarnings("ignore", message='.*"Matplotlib".*not available.*')
    import colour

from scenelens.analysis.models import PaletteColour, UInt8Image


DEFAULT_MAX_SAMPLE_PIXELS = 60_000
DEFAULT_RANDOM_SEED = 13_579
_KMEANS_LOCK = threading.Lock()


def rgb_to_oklab(rgb: NDArray[np.floating]) -> NDArray[np.float64]:
    values = np.asarray(rgb, dtype=np.float64)
    xyz = colour.sRGB_to_XYZ(values)
    return np.asarray(colour.XYZ_to_Oklab(xyz), dtype=np.float64)


def oklab_to_rgb(oklab: NDArray[np.floating]) -> NDArray[np.float64]:
    values = np.asarray(oklab, dtype=np.float64)
    xyz = colour.Oklab_to_XYZ(values)
    return np.clip(np.asarray(colour.XYZ_to_sRGB(xyz), dtype=np.float64), 0.0, 1.0)


def _resize_for_sampling(
    rgb: UInt8Image,
    mask: NDArray[np.bool_] | None,
    max_pixels: int,
) -> tuple[UInt8Image, NDArray[np.bool_] | None]:
    height, width = rgb.shape[:2]
    pixel_count = height * width
    if pixel_count <= max_pixels:
        return rgb, mask

    scale = (max_pixels / float(pixel_count)) ** 0.5
    sample_width = max(1, int(width * scale))
    sample_height = max(1, int(height * scale))
    sampled_rgb = cv2.resize(
        rgb, (sample_width, sample_height), interpolation=cv2.INTER_AREA
    )
    sampled_mask = None
    if mask is not None:
        sampled_mask = cv2.resize(
            mask.astype(np.uint8),
            (sample_width, sample_height),
            interpolation=cv2.INTER_NEAREST,
        ).astype(bool)
    return sampled_rgb, sampled_mask


def extract_oklab_palette(
    rgb: UInt8Image,
    colour_count: int = 8,
    mask: NDArray[np.bool_] | None = None,
    max_sample_pixels: int = DEFAULT_MAX_SAMPLE_PIXELS,
    random_seed: int = DEFAULT_RANDOM_SEED,
) -> tuple[tuple[PaletteColour, ...], int]:
    """Cluster a bounded spatial sample in Oklab and return area proportions."""
    if colour_count < 1:
        raise ValueError("colour_count must be positive")
    if max_sample_pixels < colour_count:
        raise ValueError("max_sample_pixels must be at least colour_count")

    sampled_rgb, sampled_mask = _resize_for_sampling(rgb, mask, max_sample_pixels)
    pixels = sampled_rgb.reshape(-1, 3)
    if sampled_mask is not None:
        pixels = pixels[sampled_mask.reshape(-1)]
    if pixels.size == 0:
        return (), 0

    unique_rgb = np.unique(pixels, axis=0)
    cluster_count = min(colour_count, len(unique_rgb), len(pixels))
    if cluster_count == 1:
        centre_rgb = pixels[0].astype(np.float64) / 255.0
        centre_oklab = rgb_to_oklab(centre_rgb[np.newaxis, :])[0]
        colour_item = PaletteColour(
            rgb=tuple(int(value) for value in pixels[0]),
            oklab=tuple(float(value) for value in centre_oklab),
            proportion=1.0,
        )
        return (colour_item,), int(len(pixels))

    pixels_float = pixels.astype(np.float64) / 255.0
    samples_oklab = rgb_to_oklab(pixels_float).astype(np.float32)
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        40,
        1e-4,
    )

    # OpenCV's RNG is process-global. Serialize the seeded call so concurrent
    # reference/current analyses remain reproducible.
    with _KMEANS_LOCK:
        cv2.setRNGSeed(int(random_seed))
        _, labels, centres = cv2.kmeans(
            samples_oklab,
            cluster_count,
            None,
            criteria,
            1,
            cv2.KMEANS_PP_CENTERS,
        )

    label_counts = np.bincount(labels.reshape(-1), minlength=cluster_count)
    centre_rgb = np.rint(oklab_to_rgb(centres) * 255.0).astype(np.uint8)
    order = np.argsort(-label_counts, kind="stable")

    palette = tuple(
        PaletteColour(
            rgb=tuple(int(value) for value in centre_rgb[index]),
            oklab=tuple(float(value) for value in centres[index]),
            proportion=float(label_counts[index] / len(labels)),
        )
        for index in order
        if label_counts[index] > 0
    )
    return palette, int(len(pixels))
