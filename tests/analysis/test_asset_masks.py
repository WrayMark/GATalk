from __future__ import annotations

import numpy as np

from scenelens.analysis.asset_masks import (
    apply_transparent_mask,
    normalized_rect_to_pixels,
    visible_asset_mask,
)


def test_normalized_asset_rect_maps_independently_of_view_size() -> None:
    rect = (0.1, 0.2, 0.5, 0.4)
    assert normalized_rect_to_pixels(rect, (100, 200, 3)) == (
        20,
        20,
        100,
        40,
    )
    assert normalized_rect_to_pixels(rect, (1000, 2000, 3)) == (
        200,
        200,
        1000,
        400,
    )


def test_visible_mask_stays_inside_evidence_rectangle() -> None:
    rgb = np.full((90, 120, 3), 20, dtype=np.uint8)
    rgb[25:70, 35:90] = (210, 90, 45)
    rect = (30 / 120, 20 / 90, 65 / 120, 55 / 90)
    mask, method = visible_asset_mask(rgb, rect)
    assert method in {"grabcut_visible_v1", "rectangle_proxy_v1"}
    assert mask.dtype == np.uint8
    assert mask.shape == rgb.shape[:2]
    assert not mask[:19].any()
    assert not mask[:, :29].any()
    assert not mask[76:].any()
    assert not mask[:, 96:].any()
    rgba = apply_transparent_mask(rgb, mask)
    assert rgba.shape == (90, 120, 4)
    assert np.array_equal(rgba[:, :, :3], rgb)

