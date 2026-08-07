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
            credential_target="GATalk/provider/mock",
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
    if title == "GATalk Asset Breakdown Advisory":
        return {
            "schema_version": "1.0",
            "reviewer_id": "asset_breakdown_advisory",
            "scene_understanding": {
                "scene_archetype": "离线流程示例",
                "summary": (
                    "离线 Mock 不读取图片语义；这里只演示先理解、再选择"
                    "拆分深度的完整流程。"
                ),
                "spatial_structure": ["前景", "主体区", "远景"],
                "production_systems": ["装配体", "复用套件", "材质系统"],
                "asset_families": [
                    {
                        "family_id": "mock_architecture",
                        "name": "示例建筑族",
                        "category": "building",
                        "role": "主体装配体",
                        "reuse_signal": "Mock 未执行真实判断。",
                        "visible_evidence": "没有实际视觉证据。",
                        "confidence": 0.0,
                    },
                    {
                        "family_id": "mock_surface",
                        "name": "示例地表系统",
                        "category": "terrain",
                        "role": "承载场景",
                        "reuse_signal": "Mock 未执行真实判断。",
                        "visible_evidence": "没有实际视觉证据。",
                        "confidence": 0.0,
                    },
                ],
                "visible_evidence": ["离线 Mock 没有读取图片。"],
                "uncertainties": ["全部语义需要用户校正或连接真实视觉模型。"],
            },
            "recommended_plans": [
                {
                    "name": "完整装配体示例",
                    "preset_id": "assembly_set",
                    "purpose": "先确认主要建筑、桥梁、岩组或植被群落。",
                    "scope": "whole_scene",
                    "category_depths": [
                        {"category": "building", "depth": 2},
                        {"category": "prop", "depth": 2},
                        {"category": "vegetation", "depth": 2},
                        {"category": "terrain", "depth": 2}
                    ],
                    "grouping_strategy": "asset_family",
                    "max_items_per_page": 9,
                    "rationale": "用于演示装配体层级。"
                },
                {
                    "name": "生产套件示例",
                    "preset_id": "production_kit",
                    "purpose": "继续规划可复用结构段、组件和材质系统。",
                    "scope": "whole_scene",
                    "category_depths": [
                        {"category": "building", "depth": 3},
                        {"category": "modular_piece", "depth": 3},
                        {"category": "prop", "depth": 3},
                        {"category": "vegetation", "depth": 3},
                        {"category": "terrain", "depth": 3},
                        {"category": "material", "depth": 3}
                    ],
                    "grouping_strategy": "hierarchy",
                    "max_items_per_page": 9,
                    "rationale": "用于演示生产套件层级。"
                }
            ]
        }
    if title == "GATalk Asset Breakdown":
        return {
            "schema_version": "1.0",
            "reviewer_id": "asset_breakdown_review",
            "scene_understanding": {
                "scene_type": "未分析",
                "summary": (
                    "离线 Mock 不读取图像语义；仅提供可编辑的示例资产结构，"
                    "用于验证保存、遮罩、生成和导出流程。"
                ),
                "spatial_layers": ["前景", "中景", "远景"],
                "breakdown_rule": "按制作职能建立示例层级，不作为真实识别结论。",
            },
            "production_strategy": {
                "hero_assets": ["示例主体"],
                "modular_kits": ["示例建筑模块"],
                "repeatable_assets": ["示例重复道具"],
                "materials_and_decals": ["示例地表材质"],
                "background_only": ["示例远景"],
            },
            "assets": [
                {
                    "asset_id": "mock_hero_structure",
                    "name": "示例主体建筑",
                    "category": "building",
                    "semantic_type": "英雄资产示例",
                    "parent_asset_id": "",
                    "level": 0,
                    "normalized_rect": [0.18, 0.18, 0.45, 0.54],
                    "evidence_kind": "ai_inference",
                    "visible_evidence": "Mock 未读取图片；此矩形只是流程示例。",
                    "inferred_details": "需由用户连接真实视觉 Provider 或手动修订。",
                    "uncertainty": "没有实际视觉证据。",
                    "confidence": 0.0,
                    "occlusion_status": "uncertain",
                    "reuse_group": "",
                    "instance_count": 1,
                    "production_priority": "high",
                    "production_strategy": "先校正区域和分类，再决定制作方式。",
                    "module_pieces": ["墙段示例", "开口示例"],
                    "variants": [],
                    "material_notes": "",
                },
                {
                    "asset_id": "mock_ground",
                    "name": "示例地表",
                    "category": "terrain",
                    "semantic_type": "地形与材质示例",
                    "parent_asset_id": "",
                    "level": 0,
                    "normalized_rect": [0.0, 0.65, 1.0, 0.35],
                    "evidence_kind": "ai_inference",
                    "visible_evidence": "Mock 未读取图片。",
                    "inferred_details": "可能需要区分几何、混合材质和贴花。",
                    "uncertainty": "没有实际视觉证据。",
                    "confidence": 0.0,
                    "occlusion_status": "none",
                    "reuse_group": "surface_example",
                    "instance_count": 1,
                    "production_priority": "medium",
                    "production_strategy": "由用户判断模型与材质边界。",
                    "module_pieces": [],
                    "variants": [],
                    "material_notes": "示例字段。",
                },
            ],
            "relationships": [],
            "uncertainties": [
                "离线 Mock 没有执行视觉推理，所有语义和矩形均为流程占位。"
            ],
        }
    if title == "GATalk Asset Prompt Workshop":
        return {
            "schema_version": "1.0",
            "reviewer_id": "asset_prompt_workshop",
            "prompt_title": "离线 Mock 资产拆分提示语",
            "target_tool": "generic",
            "analysis_summary": (
                "离线 Mock 不读取图片语义；以下内容只验证提示语编辑、"
                "对话修订、复制和保存流程。"
            ),
            "prompt_zh": (
                "根据输入场景建立一张游戏环境资产拆分展示板。"
                "将主体建筑模块、重复道具、地表材质和远景元素分开摆放，"
                "中性背景，轮廓完整，不裁切，保留统一设计语言。"
            ),
            "prompt_en": (
                "Create a game-environment asset breakdown sheet from the "
                "input scene. Separate the main modular architecture, repeated "
                "props, surface materials, and background elements on a neutral "
                "background, with complete silhouettes and no cropping."
            ),
            "negative_prompt": "不要裁切，不要重复资产，不要添加无依据细节。",
            "constraints": [
                "原画直接可见内容与推测补全分开",
                "资产之间留出清晰间距",
                "保持原画设计身份",
            ],
            "asset_groups": [
                {
                    "name": "示例主体建筑",
                    "category": "building",
                    "visible_evidence": "Mock 未读取图片。",
                    "uncertainty": "需要真实视觉模型或用户确认。",
                    "prompt_fragment_zh": "主体建筑及可复用墙段、开口与收边模块。",
                    "prompt_fragment_en": (
                        "Main structure with reusable wall, opening, and trim "
                        "modules."
                    ),
                },
                {
                    "name": "示例重复道具",
                    "category": "prop",
                    "visible_evidence": "Mock 未读取图片。",
                    "uncertainty": "数量和造型需要用户确认。",
                    "prompt_fragment_zh": "按类型成组展示重复道具和少量变体。",
                    "prompt_fragment_en": (
                        "Group repeated props by type with a few controlled "
                        "variants."
                    ),
                },
            ],
            "change_summary": "生成离线流程示例；没有执行真实图片分析。",
        }
    if title == "GATalk Artwork Master Study":
        dimensions = (
            "composition",
            "visual_hierarchy",
            "value_structure",
            "colour_design",
            "lighting",
            "spatial_depth",
            "shape_language",
            "edge_detail_control",
            "material_surface",
            "environment_storytelling",
            "style_technique",
            "emotional_impact",
        )
        return {
            "schema_version": "1.0",
            "reviewer_id": "artwork_master_study",
            "reading_scope": {
                "visible_content": "离线 Mock 不读取图片语义。",
                "assumed_context": "",
                "viewing_strategy": "仅验证十二维结构化流程。",
                "uncertainties": ["Mock 没有执行视觉模型推理。"],
            },
            "executive_thesis": (
                "离线 Mock：作品研究结构、保存和界面流程可用；"
                "此内容不是实际美术分析。"
            ),
            "dimension_studies": [
                {
                    "dimension_id": dimension,
                    "observation": "Mock 未观察图片。",
                    "visual_evidence": ["仅验证结构化字段"],
                    "measurement_evidence": [],
                    "interpretation": "连接真实视觉 Provider 后生成。",
                    "effect_on_viewer": "Mock 无法判断。",
                    "evaluation_status": "insufficient_evidence",
                    "evaluation": "证据不足，不能评价。",
                    "relationships": [],
                    "learning_points": ["Mock 输出不能作为学习结论。"],
                    "confidence": 0.0,
                    "uncertainty": "未执行视觉推理。",
                }
                for dimension in dimensions
            ],
            "causal_chains": [
                {
                    "cause": "Mock 输入",
                    "mechanism": "结构化流程验证",
                    "effect": "确认界面可以显示因果链",
                    "linked_dimensions": ["composition", "value_structure"],
                    "evidence": "仅流程证据",
                    "confidence": 0.0,
                },
                {
                    "cause": "Mock 输入",
                    "mechanism": "Schema 验证",
                    "effect": "确认十二维字段完整",
                    "linked_dimensions": ["colour_design", "lighting"],
                    "evidence": "仅流程证据",
                    "confidence": 0.0,
                },
                {
                    "cause": "Mock 输入",
                    "mechanism": "保存恢复验证",
                    "effect": "确认研究结果可以持久化",
                    "linked_dimensions": [
                        "environment_storytelling",
                        "emotional_impact",
                    ],
                    "evidence": "仅流程证据",
                    "confidence": 0.0,
                },
            ],
            "scene_breakdown": {
                "scene_content": [],
                "spatial_layers": [],
                "architecture_and_design_language": [],
                "terrain_vegetation_and_atmosphere": [],
                "materials_and_surfaces": [],
                "camera_and_perspective": [],
                "narrative_clues": [],
                "production_inferences": [],
            },
            "strengths": [],
            "limitations": [],
            "annotations": [],
            "transferable_principles": [
                "真实分析需要视觉 Provider。",
                "本地测量不等于语义判断。",
                "所有推断都应保留不确定性。",
            ],
            "study_questions": [
                "作品的第一视觉组织是什么？",
                "跨维度关系如何产生效果？",
                "哪些结论有可复核证据？",
            ],
            "confidence_notes": ["Mock 输出不能作为美术结论。"],
        }
    if title == "GATalk Art Director Review":
        return {
            "schema_version": "1.0",
            "reviewer_id": "art_director_review",
            "summary": "离线 Mock：结构化审阅流程可用，未生成真实美术结论。",
            "dimension_states": [],
            "findings": [],
            "quality_gate_results": [],
        }
    if title == "GATalk Deep Art Director Review":
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
    if title == "GATalk Lighting Review":
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
    if title == "GATalk Second Opinion":
        return {
            "schema_version": "1.0",
            "reviewer_id": "second_opinion",
            "critiques": [],
            "omissions": [],
        }
    return {"findings": []}
