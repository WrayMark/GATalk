from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence

from scenelens.core.domain import QualityGate, QualityGateState


class VersionChangeStatus(StrEnum):
    IMPROVED = "improved"
    NO_CLEAR_CHANGE = "no_clear_change"
    FURTHER_AWAY = "further_away"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class GateEvaluation:
    gate_id: str
    state: QualityGateState
    measured_value: float | None
    reason: str


@dataclass(frozen=True)
class SecondOpinionItem:
    finding_id: str
    source_provider_id: str
    status: str
    critique: str
    missing_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class MergedFinding:
    finding: Mapping[str, Any]
    primary_provider_id: str
    second_opinion_provider_id: str | None
    second_opinion_status: str | None
    disagreement: str | None


def evaluate_quality_gate(
    gate: QualityGate,
    measurements: Mapping[str, float],
) -> GateEvaluation:
    measured = measurements.get(gate.metric_key)
    if measured is None:
        return GateEvaluation(
            gate.id,
            QualityGateState.INSUFFICIENT_EVIDENCE,
            None,
            f"缺少门禁指标：{gate.metric_key}",
        )
    target = gate.threshold.get("value")
    if not isinstance(target, (int, float)):
        return GateEvaluation(
            gate.id,
            QualityGateState.INSUFFICIENT_EVIDENCE,
            float(measured),
            "门禁阈值未配置为数值。",
        )
    margin = float(gate.threshold.get("warning_margin", 0.0))
    passed, warning = _evaluate_operator(
        float(measured),
        gate.operator,
        float(target),
        margin,
    )
    if passed:
        state = QualityGateState.PASS
        reason = "用户定义的质量门禁已满足。"
    elif warning:
        state = QualityGateState.WARNING
        reason = "接近门禁阈值，需要人工复核。"
    else:
        state = QualityGateState.FAIL
        reason = "尚未满足用户定义的质量门禁。"
    return GateEvaluation(gate.id, state, float(measured), reason)


def compare_versions_to_target(
    previous_distance: float | None,
    current_distance: float | None,
    *,
    minimum_change: float = 0.02,
) -> VersionChangeStatus:
    if previous_distance is None or current_distance is None:
        return VersionChangeStatus.INSUFFICIENT_EVIDENCE
    change = previous_distance - current_distance
    if change >= minimum_change:
        return VersionChangeStatus.IMPROVED
    if change <= -minimum_change:
        return VersionChangeStatus.FURTHER_AWAY
    return VersionChangeStatus.NO_CLEAR_CHANGE


def merge_second_opinion(
    findings: Sequence[Mapping[str, Any]],
    *,
    primary_provider_id: str,
    second_provider_id: str | None,
    opinions: Sequence[SecondOpinionItem] = (),
) -> tuple[MergedFinding, ...]:
    by_id = {item.finding_id: item for item in opinions}
    merged: list[MergedFinding] = []
    for finding in findings:
        finding_id = str(finding.get("finding_id", ""))
        opinion = by_id.get(finding_id)
        disagreement = None
        if opinion is not None and opinion.status in {
            "conflict",
            "unsupported",
        }:
            disagreement = opinion.critique
        merged.append(
            MergedFinding(
                finding=dict(finding),
                primary_provider_id=primary_provider_id,
                second_opinion_provider_id=(
                    None if opinion is None else second_provider_id
                ),
                second_opinion_status=(
                    None if opinion is None else opinion.status
                ),
                disagreement=disagreement,
            )
        )
    return tuple(merged)


def build_offline_review_pack(
    *,
    reviewer_id: str,
    context: Mapping[str, Any],
    image_manifest: Sequence[Mapping[str, Any]],
    output_schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a non-network review package without embedding local paths."""

    sanitized_images = []
    for image in image_manifest:
        sanitized_images.append(
            {
                "role": str(image["role"]),
                "sha256": str(image["sha256"]),
                "media_type": str(image["media_type"]),
                "filename": str(image.get("filename", "")),
            }
        )
    return {
        "format": "scenelens.offline_review_pack",
        "format_version": 1,
        "reviewer_id": reviewer_id,
        "context": dict(context),
        "images": sanitized_images,
        "output_schema": dict(output_schema),
        "privacy_notice": (
            "该文件不会自动上传；提交外部 AI 前请按团队政策检查内容。"
        ),
    }


def _evaluate_operator(
    value: float,
    operator: str,
    target: float,
    margin: float,
) -> tuple[bool, bool]:
    if operator == ">=":
        return value >= target, value >= target - margin
    if operator == "<=":
        return value <= target, value <= target + margin
    raise ValueError(f"Unsupported quality gate operator: {operator}")
