import numpy as np
import pytest

from scenelens.analysis.comparison_distributions import (
    compare_colour_distribution,
)


def test_distribution_comparison_is_normalized_and_deterministic():
    reference = np.zeros((80, 120, 3), dtype=np.uint8)
    reference[:, :60] = (240, 45, 20)
    reference[:, 60:] = (25, 30, 35)
    current = np.full((80, 120, 3), (60, 120, 220), dtype=np.uint8)

    first = compare_colour_distribution(
        reference, current, metric="oklab_chroma", bins=32
    )
    second = compare_colour_distribution(
        reference, current, metric="oklab_chroma", bins=32
    )

    assert first == second
    assert sum(first.reference_values) == pytest.approx(1.0)
    assert sum(first.current_values) == pytest.approx(1.0)
    assert len(first.reference_values) == 32


def test_hue_distribution_excludes_neutral_pixels_without_modifying_inputs():
    reference = np.full((40, 40, 3), 128, dtype=np.uint8)
    reference[:, :10] = (255, 0, 0)
    current = np.full((40, 40, 3), 90, dtype=np.uint8)
    original = reference.copy()

    result = compare_colour_distribution(
        reference,
        current,
        metric="oklab_hue",
        bins=16,
        neutral_threshold=0.04,
    )

    assert result.reference_excluded_ratio == pytest.approx(0.75, abs=0.02)
    assert result.current_excluded_ratio == pytest.approx(1.0)
    assert sum(result.reference_values) == pytest.approx(1.0)
    assert sum(result.current_values) == pytest.approx(0.0)
    assert np.array_equal(reference, original)


@pytest.mark.parametrize("metric", [
    "relative_luminance",
    "oklab_lightness",
    "oklab_chroma",
    "oklab_hue",
    "hsv_saturation",
])
def test_all_supported_distribution_metrics(metric):
    rgb = np.full((24, 32, 3), (40, 90, 150), dtype=np.uint8)
    result = compare_colour_distribution(rgb, rgb, metric=metric, bins=64)
    assert result.reference_values == pytest.approx(result.current_values)
