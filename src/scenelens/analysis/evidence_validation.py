from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from scenelens.analysis.luminance import display_luminance
from scenelens.analysis.models import UInt8Image
from scenelens.analysis.palette import rgb_to_oklab
from scenelens.analysis.region_analysis import (
    bounded_region_colour_sample,
    crop_normalized_region,
)


class EvidenceMetric(StrEnum):
    MEAN_LUMINANCE = "mean_luminance"
    LOCAL_CONTRAST = "local_contrast"
    HIGHLIGHT_RATIO = "highlight_ratio"
    SHADOW_RATIO = "shadow_ratio"
    WARMTH_OKLAB_B = "warmth_oklab_b"
    REFERENCE_LUMINANCE_DELTA = "reference_luminance_delta"


class EvidenceStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONFLICT = "conflict"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class NormalizedBox:
    x: float
    y: float
    width: float
    height: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.width, self.height

    def validate(self) -> None:
        if (
            self.x < 0.0
            or self.y < 0.0
            or self.width <= 0.0
            or self.height <= 0.0
            or self.x + self.width > 1.0 + 1e-9
            or self.y + self.height > 1.0 + 1e-9
        ):
            raise ValueError("normalized box must be non-empty inside 0..1")


@dataclass(frozen=True)
class EvidenceExpectation:
    metric: EvidenceMetric
    operator: str
    threshold: float
    tolerance: float = 0.05

    def __post_init__(self) -> None:
        if self.operator not in {">=", "<=", "abs>="}:
            raise ValueError("operator must be >=, <= or abs>=")
        if self.tolerance < 0.0:
            raise ValueError("tolerance must not be negative")


@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: str
    description: str
    current_box: NormalizedBox
    expectation: EvidenceExpectation
    confidence: float
    reference_box: NormalizedBox | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be inside 0..1")


@dataclass(frozen=True)
class EvidenceValidation:
    claim_id: str
    status: EvidenceStatus
    measured_value: float | None
    threshold: float
    adjusted_confidence: float
    reason: str


def validate_evidence_claim(
    claim: EvidenceClaim,
    current_rgb: UInt8Image,
    reference_rgb: UInt8Image | None = None,
) -> EvidenceValidation:
    try:
        claim.current_box.validate()
        if claim.reference_box is not None:
            claim.reference_box.validate()
        measured = _measure_claim(claim, current_rgb, reference_rgb)
    except (ValueError, IndexError) as exc:
        return EvidenceValidation(
            claim_id=claim.claim_id,
            status=EvidenceStatus.UNVERIFIABLE,
            measured_value=None,
            threshold=claim.expectation.threshold,
            adjusted_confidence=claim.confidence * 0.7,
            reason=f"无法验证：{exc}",
        )

    status = _classify_expectation(measured, claim.expectation)
    multipliers = {
        EvidenceStatus.SUPPORTED: 1.0,
        EvidenceStatus.PARTIALLY_SUPPORTED: 0.8,
        EvidenceStatus.CONFLICT: 0.45,
        EvidenceStatus.UNVERIFIABLE: 0.7,
    }
    reason = {
        EvidenceStatus.SUPPORTED: "本地测量支持该推断。",
        EvidenceStatus.PARTIALLY_SUPPORTED: (
            "本地测量接近阈值，只能部分支持该推断。"
        ),
        EvidenceStatus.CONFLICT: (
            "本地测量与该推断存在冲突；结论仍显示但可信度已降低。"
        ),
        EvidenceStatus.UNVERIFIABLE: "当前证据不足，无法验证。",
    }[status]
    return EvidenceValidation(
        claim_id=claim.claim_id,
        status=status,
        measured_value=float(measured),
        threshold=claim.expectation.threshold,
        adjusted_confidence=claim.confidence * multipliers[status],
        reason=reason,
    )


def _measure_claim(
    claim: EvidenceClaim,
    current_rgb: UInt8Image,
    reference_rgb: UInt8Image | None,
) -> float:
    crop = crop_normalized_region(
        current_rgb, claim.current_box.as_tuple()
    )
    luminance = display_luminance(crop)
    metric = claim.expectation.metric
    if metric == EvidenceMetric.MEAN_LUMINANCE:
        return float(np.mean(luminance))
    if metric == EvidenceMetric.LOCAL_CONTRAST:
        return float(np.std(luminance))
    if metric == EvidenceMetric.HIGHLIGHT_RATIO:
        return float(np.mean(luminance >= 0.9))
    if metric == EvidenceMetric.SHADOW_RATIO:
        return float(np.mean(luminance <= 0.1))
    if metric == EvidenceMetric.WARMTH_OKLAB_B:
        pixels = bounded_region_colour_sample(crop, 60_000)
        oklab = rgb_to_oklab(pixels.astype(np.float64) / 255.0)
        return float(np.mean(oklab[:, 2]))
    if metric == EvidenceMetric.REFERENCE_LUMINANCE_DELTA:
        if reference_rgb is None or claim.reference_box is None:
            raise ValueError("参考差异需要参考图和参考区域")
        reference_crop = crop_normalized_region(
            reference_rgb, claim.reference_box.as_tuple()
        )
        return float(
            np.mean(luminance)
            - np.mean(display_luminance(reference_crop))
        )
    raise ValueError(f"不支持的证据指标：{metric}")


def _classify_expectation(
    value: float,
    expectation: EvidenceExpectation,
) -> EvidenceStatus:
    threshold = expectation.threshold
    tolerance = expectation.tolerance
    if expectation.operator == ">=":
        if value >= threshold:
            return EvidenceStatus.SUPPORTED
        if value >= threshold - tolerance:
            return EvidenceStatus.PARTIALLY_SUPPORTED
        return EvidenceStatus.CONFLICT
    if expectation.operator == "<=":
        if value <= threshold:
            return EvidenceStatus.SUPPORTED
        if value <= threshold + tolerance:
            return EvidenceStatus.PARTIALLY_SUPPORTED
        return EvidenceStatus.CONFLICT
    absolute = abs(value)
    if absolute >= threshold:
        return EvidenceStatus.SUPPORTED
    if absolute >= max(0.0, threshold - tolerance):
        return EvidenceStatus.PARTIALLY_SUPPORTED
    return EvidenceStatus.CONFLICT
