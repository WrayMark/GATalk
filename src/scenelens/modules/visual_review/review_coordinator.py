from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from scenelens.analysis.evidence_validation import (
    EvidenceClaim,
    EvidenceExpectation,
    EvidenceMetric,
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
        primary = self.execution.run_review(
            provider,
            request,
            credentials.get(options.provider_id, ""),
            cancellation,
        )
        validated = reviewer.validate_output(primary.output)
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
