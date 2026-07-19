from __future__ import annotations

import numpy as np
import pytest

from scenelens.analysis.luminance import three_value_ratios
from scenelens.analysis.shared_palette import (
    extract_shared_oklab_palette,
    palette_membership_mask,
)


def test_shared_palette_uses_equal_samples_and_is_reproducible():
    reference = np.zeros((90, 160, 3), dtype=np.uint8)
    current = np.zeros((120, 120, 3), dtype=np.uint8)
    reference[:, :120] = (40, 80, 120)
    reference[:, 120:] = (190, 130, 60)
    current[:, :60] = (40, 80, 120)
    current[:, 60:] = (190, 130, 60)

    first = extract_shared_oklab_palette(
        reference,
        current,
        colour_count=2,
        max_samples_per_image=2_000,
        random_seed=77,
    )
    second = extract_shared_oklab_palette(
        reference,
        current,
        colour_count=2,
        max_samples_per_image=2_000,
        random_seed=77,
    )

    assert first == second
    assert first.reference_sample_count == first.current_sample_count
    assert sum(item.reference_proportion for item in first.colours) == pytest.approx(
        1.0
    )
    assert sum(item.current_proportion for item in first.colours) == pytest.approx(
        1.0
    )
    assert sorted(
        item.reference_proportion for item in first.colours
    ) == pytest.approx([0.25, 0.75], abs=0.03)
    assert sorted(
        item.current_proportion for item in first.colours
    ) == pytest.approx([0.5, 0.5], abs=0.03)


def test_palette_mask_uses_saved_centres_without_reclustering():
    rgb = np.zeros((24, 40, 3), dtype=np.uint8)
    rgb[:, :20] = (15, 30, 60)
    rgb[:, 20:] = (220, 180, 80)
    shared = extract_shared_oklab_palette(
        rgb,
        rgb,
        colour_count=2,
        max_samples_per_image=960,
        random_seed=13,
    )
    centres = np.asarray([item.oklab for item in shared.colours])

    first_mask = palette_membership_mask(rgb, centres, 0)
    second_mask = palette_membership_mask(rgb, centres, 0)

    assert np.array_equal(first_mask, second_mask)
    assert first_mask.mean() == pytest.approx(0.5)


def test_three_value_ratios_use_adjustable_thresholds():
    rgb = np.asarray(
        [[(0, 0, 0), (128, 128, 128), (255, 255, 255)]],
        dtype=np.uint8,
    )

    ratios = three_value_ratios(rgb, 0.25, 0.75)

    assert ratios == pytest.approx((1 / 3, 1 / 3, 1 / 3))
