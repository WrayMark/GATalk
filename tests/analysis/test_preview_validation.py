import numpy as np

from scenelens.analysis.preview_validation import validate_concept_preview
from scenelens.core.domain import AIConceptPreviewStatus


def _scene() -> np.ndarray:
    image = np.full((120, 160, 3), 30, dtype=np.uint8)
    image[30:95, 45:110] = (170, 140, 90)
    image[45:75, 65:95] = (230, 210, 160)
    return image


def test_identical_preview_has_no_structure_drift() -> None:
    current = _scene()
    result = validate_concept_preview(current, current.copy(), current)
    assert result.structure_drift < 0.01
    assert result.composition_shift < 0.01
    assert result.status == AIConceptPreviewStatus.CANDIDATE


def test_large_structure_shift_is_concept_only() -> None:
    current = _scene()
    shifted = np.roll(current, 45, axis=1)
    result = validate_concept_preview(current, shifted, current)
    assert result.status == AIConceptPreviewStatus.CONCEPT_ONLY
    assert result.reasons


def test_protected_region_change_is_reported() -> None:
    current = _scene()
    preview = current.copy()
    preview[30:95, 45:110] = (0, 255, 0)
    result = validate_concept_preview(
        current,
        preview,
        current,
        protected_regions=((0.25, 0.2, 0.5, 0.65),),
    )
    assert result.protected_region_change is not None
    assert result.protected_region_change > 0.08
    assert result.status == AIConceptPreviewStatus.CONCEPT_ONLY
