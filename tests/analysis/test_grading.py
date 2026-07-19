import numpy as np

from scenelens.analysis.grading import (
    RecipeHistory,
    SafeGradeRecipe,
    apply_safe_grade,
    preview_ladder,
)
from scenelens.analysis.luminance import srgb_to_linear
from scenelens.modules.visual_review.grading_io import cube_lut_text


def _image() -> np.ndarray:
    image = np.empty((24, 32, 3), dtype=np.uint8)
    image[:] = (70, 100, 130)
    return image


def test_strength_is_actual_linear_interpolation_and_source_is_read_only() -> None:
    source = _image()
    before = source.copy()
    full = apply_safe_grade(
        source,
        SafeGradeRecipe(exposure_stops=1.0, strength_percent=100),
    )
    half = apply_safe_grade(
        source,
        SafeGradeRecipe(exposure_stops=1.0, strength_percent=50),
    )
    source_linear = srgb_to_linear(source.astype(np.float32) / 255.0)
    full_linear = srgb_to_linear(full.astype(np.float32) / 255.0)
    half_linear = srgb_to_linear(half.astype(np.float32) / 255.0)
    assert np.allclose(
        half_linear,
        (source_linear + full_linear) / 2.0,
        atol=0.01,
    )
    assert np.array_equal(source, before)


def test_region_grade_leaves_outside_pixels_unchanged() -> None:
    source = _image()
    result = apply_safe_grade(
        source,
        SafeGradeRecipe(
            exposure_stops=1.0,
            normalized_rect=(0.25, 0.25, 0.5, 0.5),
        ),
    )
    assert np.array_equal(result[0, 0], source[0, 0])
    assert not np.array_equal(result[12, 16], source[12, 16])


def test_preview_ladder_and_recipe_history_are_deterministic() -> None:
    recipe = SafeGradeRecipe(contrast=0.2)
    ladder = preview_ladder(_image(), recipe, (5, 25, 100))
    assert [item[0] for item in ladder] == [5, 25, 100]
    history = RecipeHistory()
    history.push(recipe)
    assert history.undo() == SafeGradeRecipe()
    assert history.redo() == recipe


def test_cube_export_rejects_spatial_or_image_dependent_recipes() -> None:
    text = cube_lut_text(SafeGradeRecipe(exposure_stops=0.5), size=4)
    assert "LUT_3D_SIZE 4" in text
    import pytest

    with pytest.raises(ValueError, match="区域调色"):
        cube_lut_text(
            SafeGradeRecipe(normalized_rect=(0, 0, 0.5, 0.5))
        )
    with pytest.raises(ValueError, match="参考色迁移"):
        cube_lut_text(SafeGradeRecipe(reference_colour_transfer=0.5))
