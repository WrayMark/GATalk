import copy

import pytest

from scenelens.core.schema_validation import SchemaValidationError
from scenelens.core.workspaces import WorkbenchRegistry
from scenelens.modules.example_workbench import (
    register_example_contributions,
)
from scenelens.modules.visual_review.reviews import (
    ArtDirectorReview,
    LightingReview,
    ReviewContext,
)
from scenelens.modules.visual_review.workbench import (
    register_visual_review_workbench,
)
from scenelens.providers.contracts import ProviderImage


def _context() -> ReviewContext:
    return ReviewContext(
        project_id="project",
        shot_id="shot",
        version_id="version",
        creative_intent={"目标情绪": "清晨薄雾"},
        reference_visual_brief={"整体明度": "中低调"},
        global_measurements={"dark_ratio_delta": 0.18},
        locked_goals=("保持村庄轮廓",),
    )


def _images() -> tuple[ProviderImage, ...]:
    return (
        ProviderImage("reference", "image/png", b"reference"),
        ProviderImage("current", "image/png", b"current"),
    )


def _art_output() -> dict:
    return {
        "schema_version": "1.0",
        "reviewer_id": "art_director_review",
        "summary": "当前截图焦点关系需要复核。",
        "dimension_states": [
            {
                "dimension": "视觉焦点",
                "status": "needs_attention",
                "rationale": "主体与背景明度接近。",
            }
        ],
        "findings": [
            {
                "finding_id": "finding-1",
                "observation": "主体分离度较弱。",
                "image_evidence": "主体轮廓与远景亮度接近。",
                "measurement_evidence": ["主体区域明度差 0.03"],
                "linked_image_role": "current",
                "linked_region_ids": ["region-main"],
                "impact": "第一视觉焦点不明确。",
                "recommended_action": "先拉开主体和背景的明度关系。",
                "priority": "high",
                "confidence": 0.72,
                "counterevidence_or_uncertainty": "材质仍在制作中。",
                "next_version_validation": "复测主体区域局部对比。",
            }
        ],
        "quality_gate_results": [
            {
                "gate_id": "focus-separation",
                "status": "needs_attention",
                "reason": "区域证据尚未满足用户门禁。",
            }
        ],
    }


def _lighting_output() -> dict:
    scheme = {
        "strategy": "faithful_to_reference",
        "key_direction_and_altitude": "左后方中低角度。",
        "key_softness": "保持较软阴影。",
        "key_fill_relationship": "环境填充低于主光。",
        "colour_temperature_strategy": "冷环境、暖焦点。",
        "sky_and_indirect_light": "降低天空填充。",
        "exposure_direction": "保持曝光，仅压低背景。",
        "fog_and_atmospheric_perspective": "远景雾略增强。",
        "volumetric_light": "只在焦点附近轻量使用。",
        "focus_emphasis": "提亮入口。",
        "depth_separation": "压低远景中间调。",
        "regions_to_darken_or_lift": ["压低右侧背景"],
        "ue53_execution_order": ["先校准曝光", "再调整主光"],
        "risks": ["可能压丢暗部信息"],
        "validation": ["复测三阶明度比例"],
        "annotations": [
            {
                "kind": "light_arrow",
                "points": [{"x": 0.2, "y": 0.1}, {"x": 0.5, "y": 0.5}],
                "label": "主光方向",
            }
        ],
    }
    dramatic = copy.deepcopy(scheme)
    dramatic["strategy"] = "heightened_drama"
    readable = copy.deepcopy(scheme)
    readable["strategy"] = "gameplay_readability"
    dimensions = (
        "exposure_value_range",
        "key_fill_balance",
        "focal_hierarchy",
        "depth_separation",
        "colour_temperature",
        "shadow_silhouette",
        "atmosphere_volumetrics",
        "gameplay_readability",
    )
    return {
        "schema_version": "2.0",
        "reviewer_id": "lighting_review",
        "summary": "灯光焦点可进一步集中。",
        "target_readback": {
            "production_stage": "灯光初版",
            "target_mood": "宁静",
            "primary_focus": "入口",
            "protected_content": [],
            "review_exclusions": [],
        },
        "dimension_reviews": [
            {
                "dimension_id": dimension,
                "status": "partially_meets",
                "intent_target": "建立清楚的灯光层级",
                "reference_read": "参考图用局部亮区组织焦点。",
                "current_read": "当前亮区较分散。",
                "evidence_summary": ["共享明度数据支持比较"],
                "strengths": ["入口已有亮度基础"],
                "risks": ["背景可能竞争焦点"],
                "linked_finding_ids": [],
                "confidence": 0.7,
                "uncertainty": "缺少 UE 工程灯光参数",
            }
            for dimension in dimensions
        ],
        "lighting_components": [
            {
                "component_id": "light-1",
                "inference_type": "focus_area",
                "normalized_rect": {
                    "x": 0.3,
                    "y": 0.3,
                    "width": 0.2,
                    "height": 0.2,
                },
                "image_evidence": "入口周围出现局部高亮。",
                "alternative_explanation": "也可能来自高反射材质。",
                "confidence": 0.65,
                "narrative_role": "引导玩家注意入口。",
                "ue5_component_candidates": ["Rect Light", "Spot Light"],
            }
        ],
        "findings": [],
        "preserve_items": ["入口附近已有暖色组织"],
        "action_plan": [],
        "target_schemes": [scheme, dramatic, readable],
        "performance_checklist": [
            "确认 Lumen 模式",
            "记录阴影光源数量",
        ],
        "confidence_notes": ["灯光组件类型仅为截图推断。"],
    }


def test_reviewers_build_requests_with_complete_context() -> None:
    request = ArtDirectorReview().create_request(_context(), _images())
    assert request.payload["locked_goals"] == ["保持村庄轮廓"]
    assert request.user_initiated is False
    assert "不得输出泛化总分" in request.system_instruction


def test_art_director_output_is_strict_and_limited() -> None:
    reviewer = ArtDirectorReview()
    assert reviewer.validate_output(_art_output()).reviewer_id == (
        "art_director_review"
    )
    invalid = _art_output()
    invalid["total_score"] = 8
    with pytest.raises(SchemaValidationError, match="total_score"):
        reviewer.validate_output(invalid)


def test_lighting_schema_forbids_pseudo_precise_fields() -> None:
    reviewer = LightingReview()
    assert reviewer.validate_output(_lighting_output()).reviewer_id == (
        "lighting_review"
    )
    invalid = _lighting_output()
    invalid["lighting_components"][0]["lux"] = 1200
    with pytest.raises(SchemaValidationError, match="lux"):
        reviewer.validate_output(invalid)


def test_lighting_output_requires_all_three_distinct_strategies() -> None:
    invalid = _lighting_output()
    invalid["target_schemes"][1]["strategy"] = "faithful_to_reference"
    with pytest.raises(SchemaValidationError, match="必须各包含"):
        LightingReview().validate_output(invalid)


def test_workbench_and_example_contributions_register_explicitly() -> None:
    registry = WorkbenchRegistry()
    register_visual_review_workbench(registry)
    register_example_contributions(registry)
    assert {item.workspace_id for item in registry.workspaces()} == {
        "scene_art_control",
        "example_workspace",
    }
    assert {item.reviewer_id for item in registry.reviewers()} == {
        "art_director_review",
        "deep_art_director_review",
        "lighting_review",
        "example_review",
    }
    assert registry.get_provider("example_echo").manifest.optional is True
