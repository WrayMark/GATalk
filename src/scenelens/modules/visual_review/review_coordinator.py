from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from scenelens.analysis.evidence_validation import (
    EvidenceClaim,
    EvidenceExpectation,
    EvidenceMetric,
    EvidenceStatus,
    EvidenceValidation,
    NormalizedBox,
    validate_evidence_claim,
)
from scenelens.analysis.models import UInt8Image
from scenelens.core.schema_validation import require_valid_json_schema
from scenelens.modules.visual_review.review_services import (
    MergedFinding,
    SecondOpinionItem,
    merge_second_opinion,
)
from scenelens.modules.visual_review.reviews import ReviewContext
from scenelens.modules.visual_review.reviews.base import load_review_schema
from scenelens.providers.contracts import (
    CancellationToken,
    ProviderCapability,
    ProviderImage,
    VisionReviewRequest,
)
from scenelens.providers.execution import ProviderExecutionService
from scenelens.providers.registry import ProviderRegistry


@dataclass(frozen=True)
class ReviewRunOptions:
    reviewer_id: str
    provider_id: str
    model_id: str | None = None
    second_opinion_provider_id: str | None = None
    second_opinion_model_id: str | None = None


@dataclass(frozen=True)
class ReviewRunOutcome:
    reviewer_id: str
    provider_id: str
    model_id: str
    output: Mapping[str, Any]
    component_validations: tuple[EvidenceValidation, ...]
    merged_findings: tuple[MergedFinding, ...]
    second_opinion_provider_id: str | None = None
    omissions: tuple[str, ...] = ()
    normalization_warnings: tuple[str, ...] = ()
    requested_model_id: str = ""
    attempted_model_ids: tuple[str, ...] = ()
    model_fallback_used: bool = False
    model_fallback_reason: str = ""


def review_outcome_to_payload(outcome: ReviewRunOutcome) -> dict[str, Any]:
    return {
        "format": "gatalk.visual_review.outcome",
        "format_version": 1,
        "reviewer_id": outcome.reviewer_id,
        "provider_id": outcome.provider_id,
        "model_id": outcome.model_id,
        "output": dict(outcome.output),
        "component_validations": [
            {
                "claim_id": value.claim_id,
                "status": value.status.value,
                "measured_value": value.measured_value,
                "threshold": value.threshold,
                "adjusted_confidence": value.adjusted_confidence,
                "reason": value.reason,
            }
            for value in outcome.component_validations
        ],
        "merged_findings": [
            {
                "finding": dict(value.finding),
                "primary_provider_id": value.primary_provider_id,
                "second_opinion_provider_id": value.second_opinion_provider_id,
                "second_opinion_status": value.second_opinion_status,
                "disagreement": value.disagreement,
            }
            for value in outcome.merged_findings
        ],
        "second_opinion_provider_id": outcome.second_opinion_provider_id,
        "omissions": list(outcome.omissions),
        "normalization_warnings": list(outcome.normalization_warnings),
        "requested_model_id": outcome.requested_model_id,
        "attempted_model_ids": list(outcome.attempted_model_ids),
        "model_fallback_used": outcome.model_fallback_used,
        "model_fallback_reason": outcome.model_fallback_reason,
    }


def review_outcome_from_payload(payload: Mapping[str, Any]) -> ReviewRunOutcome:
    if payload.get("format") != "gatalk.visual_review.outcome":
        output = dict(payload)
        provider_id = str(payload.get("provider_id", "历史记录"))
        return ReviewRunOutcome(
            reviewer_id=str(payload.get("reviewer_id", "")),
            provider_id=provider_id,
            model_id=str(payload.get("model_id", "")),
            output=output,
            component_validations=(),
            merged_findings=tuple(
                MergedFinding(
                    finding=dict(value),
                    primary_provider_id=provider_id,
                    second_opinion_provider_id=None,
                    second_opinion_status=None,
                    disagreement=None,
                )
                for value in output.get("findings", ())
                if isinstance(value, Mapping)
            ),
        )
    return ReviewRunOutcome(
        reviewer_id=str(payload.get("reviewer_id", "")),
        provider_id=str(payload.get("provider_id", "")),
        model_id=str(payload.get("model_id", "")),
        output=dict(payload.get("output", {})),
        component_validations=tuple(
            EvidenceValidation(
                claim_id=str(value.get("claim_id", "")),
                status=EvidenceStatus(str(value.get("status", "unverifiable"))),
                measured_value=(
                    None
                    if value.get("measured_value") is None
                    else float(value["measured_value"])
                ),
                threshold=float(value.get("threshold", 0.0)),
                adjusted_confidence=float(value.get("adjusted_confidence", 0.0)),
                reason=str(value.get("reason", "")),
            )
            for value in payload.get("component_validations", ())
            if isinstance(value, Mapping)
        ),
        merged_findings=tuple(
            MergedFinding(
                finding=dict(value.get("finding", {})),
                primary_provider_id=str(value.get("primary_provider_id", "")),
                second_opinion_provider_id=(
                    None
                    if value.get("second_opinion_provider_id") is None
                    else str(value["second_opinion_provider_id"])
                ),
                second_opinion_status=(
                    None
                    if value.get("second_opinion_status") is None
                    else str(value["second_opinion_status"])
                ),
                disagreement=(
                    None
                    if value.get("disagreement") is None
                    else str(value["disagreement"])
                ),
            )
            for value in payload.get("merged_findings", ())
            if isinstance(value, Mapping)
        ),
        second_opinion_provider_id=(
            None
            if payload.get("second_opinion_provider_id") is None
            else str(payload["second_opinion_provider_id"])
        ),
        omissions=tuple(str(value) for value in payload.get("omissions", ())),
        normalization_warnings=tuple(
            str(value) for value in payload.get("normalization_warnings", ())
        ),
        requested_model_id=str(payload.get("requested_model_id", "")),
        attempted_model_ids=tuple(
            str(value) for value in payload.get("attempted_model_ids", ())
        ),
        model_fallback_used=bool(payload.get("model_fallback_used", False)),
        model_fallback_reason=str(payload.get("model_fallback_reason", "")),
    )


class ReviewCoordinator:
    def __init__(
        self,
        providers: ProviderRegistry,
        reviewers: Mapping[str, Any],
        execution: ProviderExecutionService | None = None,
    ) -> None:
        self.providers = providers
        self.reviewers = dict(reviewers)
        self.execution = execution or ProviderExecutionService()

    def run(
        self,
        *,
        options: ReviewRunOptions,
        context: ReviewContext,
        images: tuple[ProviderImage, ...],
        current_rgb: UInt8Image,
        reference_rgb: UInt8Image,
        credentials: Mapping[str, str],
        cancellation: CancellationToken,
    ) -> ReviewRunOutcome:
        reviewer = self.reviewers[options.reviewer_id]
        provider = self.providers.get(options.provider_id)
        request = reviewer.create_request(
            context,
            images,
            model_id=options.model_id,
            user_initiated=True,
            disclosure_confirmed=True,
        )
        primary_execution = self.execution.run_review_with_model_fallback(
            provider,
            request,
            credentials.get(options.provider_id, ""),
            cancellation,
            provider.manifest.fallback_models_for(
                ProviderCapability.VISION_REVIEW,
                options.model_id,
            ),
        )
        primary = primary_execution.response
        normalized_output, normalization_warnings = (
            reviewer.normalize_output(primary.output)
        )
        validated = reviewer.validate_output(normalized_output)
        component_validations = (
            validate_lighting_components(
                validated.output,
                current_rgb,
                reference_rgb,
            )
            + validate_structured_evidence_claims(
                validated.output,
                current_rgb,
                reference_rgb,
            )
        )

        opinions: tuple[SecondOpinionItem, ...] = ()
        omissions: tuple[str, ...] = ()
        second_provider_id = options.second_opinion_provider_id
        if second_provider_id:
            cancellation.raise_if_cancelled()
            second_provider = self.providers.get(second_provider_id)
            second_schema = load_review_schema(
                "second_opinion.schema.json"
            )
            second_request = VisionReviewRequest(
                system_instruction=(
                    "你是第二意见审查器。只审查主模型发现的证据、遗漏和可疑"
                    "推断；不得重写一篇完整报告。保留 finding_id，只输出给定"
                    " JSON Schema。"
                ),
                payload={
                    "review_context": context.to_payload(),
                    "primary_provider_id": primary.provider_id,
                    "primary_model_id": primary.model_id,
                    "primary_output": dict(validated.output),
                    "local_component_validation": [
                        {
                            "claim_id": item.claim_id,
                            "status": item.status.value,
                            "measured_value": item.measured_value,
                            "reason": item.reason,
                        }
                        for item in component_validations
                    ],
                },
                images=images,
                output_schema=second_schema,
                model_id=options.second_opinion_model_id,
                user_initiated=True,
                disclosure_confirmed=True,
                max_output_tokens=4000,
            )
            second = self.execution.run_review(
                second_provider,
                second_request,
                credentials.get(second_provider_id, ""),
                cancellation,
            )
            require_valid_json_schema(second.output, second_schema)
            opinions = tuple(
                SecondOpinionItem(
                    finding_id=str(item["finding_id"]),
                    source_provider_id=second.provider_id,
                    status=str(item["status"]),
                    critique=str(item["critique"]),
                    missing_evidence=tuple(item["missing_evidence"]),
                )
                for item in second.output["critiques"]
            )
            omissions = tuple(str(item) for item in second.output["omissions"])

        merged = merge_second_opinion(
            validated.output.get("findings", []),
            primary_provider_id=primary.provider_id,
            second_provider_id=second_provider_id,
            opinions=opinions,
        )
        return ReviewRunOutcome(
            reviewer_id=options.reviewer_id,
            provider_id=primary.provider_id,
            model_id=primary.model_id,
            output=dict(validated.output),
            component_validations=component_validations,
            merged_findings=merged,
            second_opinion_provider_id=second_provider_id,
            omissions=omissions,
            normalization_warnings=normalization_warnings,
            requested_model_id=primary_execution.requested_model_id,
            attempted_model_ids=primary_execution.attempted_model_ids,
            model_fallback_used=primary_execution.fallback_used,
            model_fallback_reason=primary_execution.fallback_reason,
        )

    def close(self) -> None:
        self.execution.close()


def validate_lighting_components(
    output: Mapping[str, Any],
    current_rgb: UInt8Image,
    reference_rgb: UInt8Image,
) -> tuple[EvidenceValidation, ...]:
    del reference_rgb
    mappings: dict[str, tuple[EvidenceMetric, str, float, float]] = {
        "key_light_area": (
            EvidenceMetric.MEAN_LUMINANCE,
            ">=",
            0.5,
            0.08,
        ),
        "fill_light_area": (
            EvidenceMetric.LOCAL_CONTRAST,
            "<=",
            0.25,
            0.05,
        ),
        "focus_area": (
            EvidenceMetric.LOCAL_CONTRAST,
            ">=",
            0.08,
            0.03,
        ),
        "shadow_area": (
            EvidenceMetric.MEAN_LUMINANCE,
            "<=",
            0.35,
            0.08,
        ),
        "overexposed_area": (
            EvidenceMetric.HIGHLIGHT_RATIO,
            ">=",
            0.05,
            0.03,
        ),
        "cool_space": (
            EvidenceMetric.WARMTH_OKLAB_B,
            "<=",
            -0.01,
            0.025,
        ),
        "warm_accent": (
            EvidenceMetric.WARMTH_OKLAB_B,
            ">=",
            0.02,
            0.025,
        ),
        "silhouette_shaping": (
            EvidenceMetric.LOCAL_CONTRAST,
            ">=",
            0.1,
            0.04,
        ),
        "stage_separation": (
            EvidenceMetric.LOCAL_CONTRAST,
            ">=",
            0.08,
            0.04,
        ),
        "player_guidance_light": (
            EvidenceMetric.LOCAL_CONTRAST,
            ">=",
            0.08,
            0.04,
        ),
        "information_suppression_area": (
            EvidenceMetric.MEAN_LUMINANCE,
            "<=",
            0.45,
            0.08,
        ),
    }
    validations = []
    for component in output.get("lighting_components", []):
        inference_type = str(component["inference_type"])
        mapping = mappings.get(inference_type)
        if mapping is None:
            continue
        rect = component["normalized_rect"]
        metric, operator, threshold, tolerance = mapping
        claim = EvidenceClaim(
            claim_id=str(component["component_id"]),
            description=str(component["image_evidence"]),
            current_box=NormalizedBox(
                float(rect["x"]),
                float(rect["y"]),
                float(rect["width"]),
                float(rect["height"]),
            ),
            expectation=EvidenceExpectation(
                metric,
                operator,
                threshold,
                tolerance,
            ),
            confidence=float(component["confidence"]),
        )
        validations.append(
            validate_evidence_claim(claim, current_rgb)
        )
    return tuple(validations)


def validate_structured_evidence_claims(
    output: Mapping[str, Any],
    current_rgb: UInt8Image,
    reference_rgb: UInt8Image,
) -> tuple[EvidenceValidation, ...]:
    """Validate reviewer-authored measurable claims against local pixels."""

    validations: list[EvidenceValidation] = []
    for finding in output.get("findings", []):
        for value in finding.get("evidence_claims", []):
            current_rect = value["current_rect"]
            reference_value = value.get("reference_rect")
            reference_box = (
                None
                if reference_value is None
                else NormalizedBox(
                    float(reference_value["x"]),
                    float(reference_value["y"]),
                    float(reference_value["width"]),
                    float(reference_value["height"]),
                )
            )
            claim = EvidenceClaim(
                claim_id=str(value["claim_id"]),
                description=str(value["description"]),
                current_box=NormalizedBox(
                    float(current_rect["x"]),
                    float(current_rect["y"]),
                    float(current_rect["width"]),
                    float(current_rect["height"]),
                ),
                reference_box=reference_box,
                expectation=EvidenceExpectation(
                    EvidenceMetric(str(value["metric"])),
                    str(value["operator"]),
                    float(value["threshold"]),
                    float(value["tolerance"]),
                ),
                confidence=float(value["confidence"]),
            )
            validations.append(
                validate_evidence_claim(
                    claim,
                    current_rgb,
                    reference_rgb,
                )
            )
    return tuple(validations)
