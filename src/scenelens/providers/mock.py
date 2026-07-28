from __future__ import annotations

import json
from typing import Any, Mapping

from scenelens.providers.contracts import (
    CancellationToken,
    ImageEditRequest,
    ImageEditResponse,
    ProviderCapability,
    ProviderManifest,
    ProviderResponse,
    StructuredOutputRequest,
    VisionReviewRequest,
    require_user_approval,
)


class MockProvider:
    def __init__(
        self,
        output: Mapping[str, Any] | None = None,
        image_bytes: bytes | None = None,
    ) -> None:
        self.manifest = ProviderManifest(
            provider_id="mock",
            display_name="离线 Mock",
            api_style="mock",
            base_url="",
            capabilities=(
                ProviderCapability.VISION_REVIEW,
                ProviderCapability.STRUCTURED_OUTPUT,
                ProviderCapability.IMAGE_EDIT,
            ),
            default_models={
                ProviderCapability.VISION_REVIEW.value: "mock-vision-v1",
                ProviderCapability.STRUCTURED_OUTPUT.value: "mock-json-v1",
                ProviderCapability.IMAGE_EDIT.value: "mock-image-v1",
            },
            credential_target="SceneLens/provider/mock",
            optional=False,
            mainland_priority=0,
        )
        self.output = None if output is None else dict(output)
        self.image_bytes = (
            None if image_bytes is None else bytes(image_bytes)
        )

    def review(
        self,
        request: VisionReviewRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        del credential
        require_user_approval(request)
        cancellation.raise_if_cancelled()
        return ProviderResponse(
            provider_id=self.manifest.provider_id,
            model_id=self.manifest.model_for(
                ProviderCapability.VISION_REVIEW,
                request.model_id,
            ),
            output=json.loads(
                json.dumps(
                    self.output
                    if self.output is not None
                    else _default_mock_output(request.output_schema)
                )
            ),
        )

    def generate_structured(
        self,
        request: StructuredOutputRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ProviderResponse:
        del credential
        require_user_approval(request)
        cancellation.raise_if_cancelled()
        return ProviderResponse(
            provider_id=self.manifest.provider_id,
            model_id=self.manifest.model_for(
                ProviderCapability.STRUCTURED_OUTPUT,
                request.model_id,
            ),
            output=json.loads(
                json.dumps(
                    self.output
                    if self.output is not None
                    else _default_mock_output(request.output_schema)
                )
            ),
        )

    def edit_image(
        self,
        request: ImageEditRequest,
        credential: str,
        cancellation: CancellationToken,
    ) -> ImageEditResponse:
        del credential
        require_user_approval(request)
        cancellation.raise_if_cancelled()
        return ImageEditResponse(
            provider_id=self.manifest.provider_id,
            model_id=self.manifest.model_for(
                ProviderCapability.IMAGE_EDIT,
                request.model_id,
            ),
            media_type="image/png",
            image_bytes=(
                self.image_bytes
                if self.image_bytes is not None
                else request.images[-1].data
            ),
            metadata={"change_budget": request.change_budget},
        )


def _default_mock_output(schema: Mapping[str, Any]) -> dict[str, Any]:
    title = str(schema.get("title", ""))
    if title == "SceneLens Art Director Review":
        return {
            "schema_version": "1.0",
            "reviewer_id": "art_director_review",
            "summary": "离线 Mock：结构化审阅流程可用，未生成真实美术结论。",
            "dimension_states": [],
            "findings": [],
            "quality_gate_results": [],
        }
    if title == "SceneLens Deep Art Director Review":
        dimensions = (
            "composition",
            "visual_guidance",
            "focus_hierarchy",
            "colour_design",
            "value_structure",
            "lighting_atmosphere",
            "material_readability",
            "world_design_narrative",
        )
        return {
            "schema_version": "2.0",
            "reviewer_id": "deep_art_director_review",
            "executive_summary": (
                "离线 Mock：八维结构、证据字段和执行顺序可用；"
                "未生成真实美术结论。"
            ),
            "target_readback": {
                "production_stage": "Mock 未分析",
                "target_style": "Mock 未分析",
                "target_mood": "Mock 未分析",
                "primary_focus": "Mock 未分析",
                "protected_content": [],
                "review_exclusions": [],
            },
            "dimension_reviews": [
                {
                    "dimension_id": dimension,
                    "status": "insufficient_evidence",
                    "intent_target": "连接真实视觉 Provider 后分析",
                    "reference_read": "Mock 不读取图片语义",
                    "current_read": "Mock 不读取图片语义",
                    "evidence_summary": ["仅验证结构化流程"],
                    "strengths": [],
                    "risks": [],
                    "linked_finding_ids": [],
                    "confidence": 0.0,
                    "uncertainty": "离线 Mock 不执行本地或模型推理",
                }
                for dimension in dimensions
            ],
            "findings": [],
            "preserve_items": [],
            "action_plan": [],
            "quality_gate_results": [],
            "confidence_notes": ["Mock 输出不能作为美术结论。"],
        }
    if title == "SceneLens Lighting Review":
        schemes = []
        for strategy in (
            "faithful_to_reference",
            "heightened_drama",
            "gameplay_readability",
        ):
            schemes.append(
                {
                    "strategy": strategy,
                    "key_direction_and_altitude": "Mock 未分析",
                    "key_softness": "Mock 未分析",
                    "key_fill_relationship": "Mock 未分析",
                    "colour_temperature_strategy": "Mock 未分析",
                    "sky_and_indirect_light": "Mock 未分析",
                    "exposure_direction": "Mock 未分析",
                    "fog_and_atmospheric_perspective": "Mock 未分析",
                    "volumetric_light": "Mock 未分析",
                    "focus_emphasis": "Mock 未分析",
                    "depth_separation": "Mock 未分析",
                    "regions_to_darken_or_lift": [],
                    "ue53_execution_order": ["连接真实 Provider 后生成"],
                    "risks": [],
                    "validation": ["仅验证结构化流程"],
                    "annotations": [],
                }
            )
        return {
            "schema_version": "1.0",
            "reviewer_id": "lighting_review",
            "summary": "离线 Mock：结构化灯光审阅流程可用。",
            "lighting_components": [],
            "findings": [],
            "target_schemes": schemes,
            "performance_checklist": [],
        }
    if title == "SceneLens Second Opinion":
        return {
            "schema_version": "1.0",
            "reviewer_id": "second_opinion",
            "critiques": [],
            "omissions": [],
        }
    return {"findings": []}
