import numpy as np
import pytest

from scenelens.analysis.palette import extract_oklab_palette


def test_oklab_palette_is_deterministic_and_preserves_area_ratio():
    rgb = np.empty((100, 100, 3), dtype=np.uint8)
    rgb[:, :80] = (220, 35, 30)
    rgb[:, 80:] = (25, 55, 220)

    first, sampled_first = extract_oklab_palette(rgb, colour_count=2)
    second, sampled_second = extract_oklab_palette(rgb, colour_count=2)

    assert first == second
    assert sampled_first == sampled_second == 10_000
    assert first[0].proportion == pytest.approx(0.8, abs=0.01)
    assert first[1].proportion == pytest.approx(0.2, abs=0.01)
    assert sum(item.proportion for item in first) == pytest.approx(1.0)


def test_uniform_image_returns_one_colour_instead_of_duplicate_swatches():
    rgb = np.full((40, 50, 3), (80, 120, 160), dtype=np.uint8)

    palette, sampled = extract_oklab_palette(rgb, colour_count=8)

    assert sampled == 2_000
    assert len(palette) == 1
    assert palette[0].rgb == (80, 120, 160)
    assert palette[0].proportion == pytest.approx(1.0)


@pytest.mark.slow
def test_4k_palette_uses_bounded_sample():
    rgb = np.empty((2160, 3840, 3), dtype=np.uint8)
    rgb[:, :1920] = (35, 70, 105)
    rgb[:, 1920:] = (185, 145, 75)

    palette, sampled = extract_oklab_palette(rgb, colour_count=8)

    assert sampled <= 60_000
    assert len(palette) == 2
    assert sum(item.proportion for item in palette) == pytest.approx(1.0)

