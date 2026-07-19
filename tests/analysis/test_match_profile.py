import numpy as np

from scenelens.analysis.match_profile import build_match_profile
from scenelens.analysis.models import SharedPaletteColour, SharedPaletteResult


def _solid(value):
    image = np.empty((40, 60, 3), dtype=np.uint8)
    image[:] = value
    return image


def test_match_profile_is_transparent_and_reports_coverage() -> None:
    profile = build_match_profile(
        _solid((80, 90, 100)),
        _solid((80, 90, 100)),
    )
    assert profile.estimated_match is not None
    assert profile.estimated_match > 0.99
    unavailable = {
        item.dimension_id
        for item in profile.dimensions
        if item.similarity is None
    }
    assert {"visual_focus", "lighting_atmosphere", "spatial_depth"} <= (
        unavailable
    )
    assert 0.0 < profile.evidence_coverage < 1.0


def test_user_weights_change_estimated_match_without_hiding_dimensions() -> None:
    reference = _solid((40, 40, 40))
    current = _solid((180, 180, 180))
    shared = SharedPaletteResult(
        colours=(
            SharedPaletteColour(
                (20, 20, 20),
                (0.2, 0.0, 0.0),
                1.0,
                1.0,
            ),
        ),
        reference_sample_count=100,
        current_sample_count=100,
    )
    luminance_weighted = build_match_profile(
        reference,
        current,
        shared_palette=shared,
        weights={
            "luminance_structure": 10.0,
            "palette_area": 0.1,
        },
    )
    palette_weighted = build_match_profile(
        reference,
        current,
        shared_palette=shared,
        weights={
            "luminance_structure": 0.1,
            "palette_area": 10.0,
        },
    )
    assert (
        palette_weighted.estimated_match
        > luminance_weighted.estimated_match
    )
    assert len(palette_weighted.dimensions) == 10
