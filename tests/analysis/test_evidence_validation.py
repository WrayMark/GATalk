import numpy as np

from scenelens.analysis.evidence_validation import (
    EvidenceClaim,
    EvidenceExpectation,
    EvidenceMetric,
    EvidenceStatus,
    NormalizedBox,
    validate_evidence_claim,
)


def _solid(value: tuple[int, int, int]) -> np.ndarray:
    image = np.empty((40, 40, 3), dtype=np.uint8)
    image[:] = value
    return image


def _claim(
    metric: EvidenceMetric,
    operator: str,
    threshold: float,
    confidence: float = 0.8,
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id="claim",
        description="test",
        current_box=NormalizedBox(0.0, 0.0, 1.0, 1.0),
        expectation=EvidenceExpectation(
            metric,
            operator,
            threshold,
            tolerance=0.03,
        ),
        confidence=confidence,
    )


def test_bright_region_is_supported_by_local_measurement() -> None:
    result = validate_evidence_claim(
        _claim(EvidenceMetric.MEAN_LUMINANCE, ">=", 0.8),
        _solid((245, 245, 245)),
    )
    assert result.status == EvidenceStatus.SUPPORTED
    assert result.adjusted_confidence == 0.8


def test_conflicting_claim_remains_visible_and_lowers_confidence() -> None:
    result = validate_evidence_claim(
        _claim(EvidenceMetric.MEAN_LUMINANCE, ">=", 0.8),
        _solid((20, 20, 20)),
    )
    assert result.status == EvidenceStatus.CONFLICT
    assert result.adjusted_confidence == 0.8 * 0.45
    assert "仍显示" in result.reason


def test_warm_and_cool_regions_have_opposite_oklab_evidence() -> None:
    warm = validate_evidence_claim(
        _claim(EvidenceMetric.WARMTH_OKLAB_B, ">=", 0.04),
        _solid((240, 155, 55)),
    )
    cool = validate_evidence_claim(
        _claim(EvidenceMetric.WARMTH_OKLAB_B, "<=", -0.02),
        _solid((55, 110, 240)),
    )
    assert warm.status == EvidenceStatus.SUPPORTED
    assert cool.status == EvidenceStatus.SUPPORTED


def test_reference_difference_requires_both_images_and_boxes() -> None:
    claim = _claim(
        EvidenceMetric.REFERENCE_LUMINANCE_DELTA,
        "abs>=",
        0.2,
    )
    result = validate_evidence_claim(claim, _solid((100, 100, 100)))
    assert result.status == EvidenceStatus.UNVERIFIABLE
    assert result.measured_value is None


def test_reference_difference_can_be_measured() -> None:
    claim = EvidenceClaim(
        claim_id="delta",
        description="current is brighter",
        current_box=NormalizedBox(0, 0, 1, 1),
        reference_box=NormalizedBox(0, 0, 1, 1),
        expectation=EvidenceExpectation(
            EvidenceMetric.REFERENCE_LUMINANCE_DELTA,
            ">=",
            0.4,
        ),
        confidence=0.9,
    )
    result = validate_evidence_claim(
        claim,
        _solid((240, 240, 240)),
        _solid((30, 30, 30)),
    )
    assert result.status == EvidenceStatus.SUPPORTED
