from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import cv2
import numpy as np

from scenelens.analysis.luminance import display_luminance
from scenelens.analysis.models import UInt8Image
from scenelens.analysis.region_analysis import crop_normalized_region
from scenelens.core.domain import AIConceptPreviewStatus


@dataclass(frozen=True)
class PreviewValidationThresholds:
    structure_drift_concept_only: float = 0.12
    protected_change_concept_only: float = 0.08
    composition_shift_concept_only: float = 0.08


@dataclass(frozen=True)
class PreviewValidation:
    structure_drift: float
    stable_region_change: float | None
    protected_region_change: float | None
    composition_shift: float
    target_improvement: float
    status: AIConceptPreviewStatus
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        value = asdict(self)
        value["status"] = self.status.value
        return value


def validate_concept_preview(
    current_rgb: UInt8Image,
    preview_rgb: UInt8Image,
    reference_rgb: UInt8Image,
    *,
    stable_regions: Sequence[
        tuple[float, float, float, float]
    ] = (),
    protected_regions: Sequence[
        tuple[float, float, float, float]
    ] = (),
    thresholds: PreviewValidationThresholds | None = None,
) -> PreviewValidation:
    limits = thresholds or PreviewValidationThresholds()
    current, preview, reference = _normalize_for_comparison(
        current_rgb,
        preview_rgb,
        reference_rgb,
    )
    structure = _structure_drift(current, preview)
    composition = _composition_shift(current, preview)
    stable_change = _maximum_region_change(
        current, preview, stable_regions
    )
    protected_change = _maximum_region_change(
        current, preview, protected_regions
    )
    target_improvement = _target_improvement(
        reference,
        current,
        preview,
    )
    reasons = []
    if structure > limits.structure_drift_concept_only:
        reasons.append("结构漂移超过阈值")
    if (
        protected_change is not None
        and protected_change > limits.protected_change_concept_only
    ):
        reasons.append("用户保护区变化超过阈值")
    if composition > limits.composition_shift_concept_only:
        reasons.append("构图偏移超过阈值")
    status = (
        AIConceptPreviewStatus.CONCEPT_ONLY
        if reasons
        else AIConceptPreviewStatus.CANDIDATE
    )
    return PreviewValidation(
        structure_drift=structure,
        stable_region_change=stable_change,
        protected_region_change=protected_change,
        composition_shift=composition,
        target_improvement=target_improvement,
        status=status,
        reasons=tuple(reasons),
    )


def _normalize_for_comparison(
    current: UInt8Image,
    preview: UInt8Image,
    reference: UInt8Image,
) -> tuple[UInt8Image, UInt8Image, UInt8Image]:
    _validate_rgb(current)
    _validate_rgb(preview)
    _validate_rgb(reference)
    height, width = current.shape[:2]
    maximum_side = 512
    scale = min(1.0, maximum_side / float(max(height, width)))
    target = (
        max(8, int(round(width * scale))),
        max(8, int(round(height * scale))),
    )
    return tuple(
        np.ascontiguousarray(
            cv2.resize(image, target, interpolation=cv2.INTER_AREA)
        )
        for image in (current, preview, reference)
    )  # type: ignore[return-value]


def _structure_drift(current: UInt8Image, preview: UInt8Image) -> float:
    current_gray = np.rint(display_luminance(current) * 255).astype(
        np.uint8
    )
    preview_gray = np.rint(display_luminance(preview) * 255).astype(
        np.uint8
    )
    current_edges = cv2.Canny(current_gray, 70, 150) > 0
    preview_edges = cv2.Canny(preview_gray, 70, 150) > 0
    if not np.any(current_edges) and not np.any(preview_edges):
        return 0.0
    if not np.any(current_edges) or not np.any(preview_edges):
        return 1.0
    current_distance = cv2.distanceTransform(
        (~current_edges).astype(np.uint8),
        cv2.DIST_L2,
        3,
    )
    preview_distance = cv2.distanceTransform(
        (~preview_edges).astype(np.uint8),
        cv2.DIST_L2,
        3,
    )
    diagonal = float(np.hypot(*current_gray.shape))
    bidirectional = (
        float(np.mean(current_distance[preview_edges]))
        + float(np.mean(preview_distance[current_edges]))
    ) / (2.0 * diagonal)
    density = abs(
        float(np.mean(current_edges)) - float(np.mean(preview_edges))
    )
    return float(np.clip(bidirectional * 4.0 + density, 0.0, 1.0))


def _composition_shift(current: UInt8Image, preview: UInt8Image) -> float:
    left = display_luminance(current).astype(np.float32)
    right = display_luminance(preview).astype(np.float32)
    shift, response = cv2.phaseCorrelate(left, right)
    if not np.isfinite(response) or response < 0.01:
        return 1.0
    diagonal = float(np.hypot(current.shape[0], current.shape[1]))
    return float(np.clip(np.hypot(*shift) / diagonal, 0.0, 1.0))


def _maximum_region_change(
    current: UInt8Image,
    preview: UInt8Image,
    regions: Sequence[tuple[float, float, float, float]],
) -> float | None:
    if not regions:
        return None
    changes = []
    for rect in regions:
        left = crop_normalized_region(current, rect).astype(np.float32) / 255
        right = crop_normalized_region(preview, rect).astype(np.float32) / 255
        changes.append(float(np.mean(np.abs(left - right))))
    return max(changes)


def _target_improvement(
    reference: UInt8Image,
    current: UInt8Image,
    preview: UInt8Image,
) -> float:
    reference_hist, _ = np.histogram(
        display_luminance(reference), bins=64, range=(0.0, 1.0)
    )
    current_hist, _ = np.histogram(
        display_luminance(current), bins=64, range=(0.0, 1.0)
    )
    preview_hist, _ = np.histogram(
        display_luminance(preview), bins=64, range=(0.0, 1.0)
    )
    reference_hist = reference_hist / max(1, reference_hist.sum())
    current_hist = current_hist / max(1, current_hist.sum())
    preview_hist = preview_hist / max(1, preview_hist.sum())
    current_distance = 0.5 * np.abs(
        reference_hist - current_hist
    ).sum()
    preview_distance = 0.5 * np.abs(
        reference_hist - preview_hist
    ).sum()
    return float(np.clip(current_distance - preview_distance, -1.0, 1.0))


def _validate_rgb(rgb: UInt8Image) -> None:
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be uint8 with shape (height, width, 3)")
