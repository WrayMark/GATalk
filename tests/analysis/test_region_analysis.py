from __future__ import annotations

import time

import numpy as np
import pytest

from scenelens.analysis.palette import rgb_to_oklab
from scenelens.analysis.region_analysis import (
    analyze_paired_regions,
    analyze_region,
    render_region_palette_source_mask,
)


def _centres(*rgb_colours: tuple[int, int, int]) -> np.ndarray:
    rgb = np.asarray(rgb_colours, dtype=np.float64) / 255.0
    return rgb_to_oklab(rgb)


def test_region_luminance_percentiles_and_three_value_ratios_are_measured():
    rgb = np.zeros((20, 20, 3), dtype=np.uint8)
    rgb[:, 10:] = 255
    result = analyze_region(
        rgb,
        (0.0, 0.0, 1.0, 1.0),
        _centres((0, 0, 0), (255, 255, 255)),
        low_threshold=0.25,
        high_threshold=0.75,
    )

    assert result.pixel_count == 400
    assert result.mean_linear_luminance == pytest.approx(0.5)
    assert result.luminance_standard_deviation == pytest.approx(0.5)
    assert result.luminance_p10 == pytest.approx(0.0)
    assert result.luminance_p50 == pytest.approx(0.5)
    assert result.luminance_p90 == pytest.approx(1.0)
    assert result.effective_luminance_span == pytest.approx(1.0)
    assert result.three_value_ratios == pytest.approx((0.5, 0.0, 0.5))
    assert sum(result.shared_palette_proportions) == pytest.approx(1.0)


def test_low_chroma_pixels_are_excluded_from_hue_statistics():
    rgb = np.zeros((20, 20, 3), dtype=np.uint8)
    rgb[:, :10] = (128, 128, 128)
    rgb[:, 10:] = (255, 0, 0)
    result = analyze_region(
        rgb,
        (0.0, 0.0, 1.0, 1.0),
        _centres((128, 128, 128), (255, 0, 0)),
        neutral_chroma_threshold=0.03,
        hue_bins=12,
    )

    assert result.neutral_ratio == pytest.approx(0.5)
    assert result.chromatic_pixel_count == 200
    assert result.hue_mean_degrees is not None
    assert result.hue_mean_degrees == pytest.approx(29.2, abs=1.0)
    assert sum(result.hue_distribution) == pytest.approx(1.0)
    assert sum(result.shared_palette_proportions) == pytest.approx(1.0)


def test_paired_analysis_uses_same_palette_centres_for_both_regions():
    reference = np.full((40, 60, 3), (30, 60, 110), dtype=np.uint8)
    current = np.full((40, 60, 3), (190, 120, 50), dtype=np.uint8)
    centres = _centres((30, 60, 110), (190, 120, 50))

    result = analyze_paired_regions(
        reference,
        current,
        (0.1, 0.1, 0.8, 0.8),
        (0.2, 0.2, 0.6, 0.6),
        centres,
    )

    assert result.reference.shared_palette_proportions == pytest.approx(
        (1.0, 0.0)
    )
    assert result.current.shared_palette_proportions == pytest.approx(
        (0.0, 1.0)
    )
    assert result.reference.mean_linear_luminance != pytest.approx(
        result.current.mean_linear_luminance
    )


def test_region_palette_mask_is_limited_to_selected_pair_geometry():
    rgb = np.zeros((20, 40, 3), dtype=np.uint8)
    rgb[:, :20] = (20, 50, 100)
    rgb[:, 20:] = (220, 170, 60)
    centres = _centres((20, 50, 100), (220, 170, 60))

    preview = render_region_palette_source_mask(
        rgb,
        (0.0, 0.0, 0.5, 1.0),
        centres,
        0,
    )

    assert np.array_equal(preview[:, :20], rgb[:, :20])
    assert np.all(preview[:, 20:] < rgb[:, 20:])


@pytest.mark.slow
def test_4k_typical_region_analysis_finishes_with_bounded_colour_sampling():
    height, width = 2160, 3840
    x = np.linspace(0, 255, width, dtype=np.uint8)
    y = np.linspace(0, 255, height, dtype=np.uint8)[:, np.newaxis]
    reference = np.empty((height, width, 3), dtype=np.uint8)
    reference[..., 0] = x
    reference[..., 1] = y
    reference[..., 2] = 96
    current = np.ascontiguousarray(reference[:, ::-1])
    centres = _centres(
        (20, 30, 70),
        (80, 100, 110),
        (150, 130, 100),
        (230, 210, 120),
    )

    started = time.perf_counter()
    result = analyze_paired_regions(
        reference,
        current,
        (0.1, 0.1, 0.6, 0.65),
        (0.15, 0.12, 0.6, 0.65),
        centres,
        max_colour_samples=100_000,
    )
    elapsed = time.perf_counter() - started

    assert result.reference.colour_sample_count <= 100_000
    assert result.current.colour_sample_count <= 100_000
    assert elapsed < 10.0
