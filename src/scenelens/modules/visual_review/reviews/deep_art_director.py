from __future__ import annotations

from scenelens.core.schema_validation import (
    SchemaIssue,
    SchemaValidationError,
)
from scenelens.core.workspaces import ReviewerDescriptor

from .base import (
    StructuredVisionReviewer,
    ValidatedReview,
    load_review_schema,
)


DEEP_REVIEW_DIMENSIONS = (
    "composition",
    "visual_guidance",
    "focus_hierarchy",
    "colour_design",
    "value_structure",
    "lighting_atmosphere",
    "material_readability",
    "world_design_narrative",
)


class DeepArtDirectorReview(StructuredVisionReviewer):
    schema_filename = "deep_art_director_review.schema.json"
    max_output_tokens = 12000
    system_instruction = (
        "你是资深游戏场景主美，执行一次证据化八维深度审阅。首先复述用户的"
        "制作阶段、目标、焦点、保留项和暂不审阅项；白盒、灯光初版等阶段必须"
        "使用相应成熟度标准。然后严格按 composition、visual_guidance、"
        "focus_hierarchy、colour_design、value_structure、"
        "lighting_atmosphere、material_readability、"
        "world_design_narrative 八个维度逐项比较：制作意图希望什么、参考图"
        "呈现什么、当前截图实际是什么。不得把空间九宫格代理当作显著性真相，"
        "不得虚构测量值、UE 工程设置、材质参数、Lux、EV 或性能收益。"
        "只有 payload 中存在的数值才能写入 measurement_evidence；视觉判断必须"
        "写出画面依据和不确定性。保留当前有效优点，最多提炼五个跨维度核心"
        "问题，并给出有依赖顺序的 UE 执行动作和下一版本验证方法。需要本地像素"
        "复核的结论必须填写 evidence_claims；若没有合适的可测指标则留空，"
        "不能伪造阈值。不得输出总分。只输出符合给定 JSON Schema 的 JSON。"
    )
    descriptor = ReviewerDescriptor(
        module_id="scenelens.visual_review",
        reviewer_id="deep_art_director_review",
        display_name="深度主美审阅（八维）",
        version="2.0.0",
        supported_inputs=(
            "creative_intent",
            "reference_visual_brief",
            "reference_image",
            "current_image",
            "global_measurements",
            "local_evidence_digest",
            "paired_region_measurements",
            "version_history",
            "locked_goals",
            "quality_gates",
            "production_context",
        ),
        output_schema=load_review_schema(
            "deep_art_director_review.schema.json"
        ),
    )

    def validate_output(self, output) -> ValidatedReview:
        validated = super().validate_output(output)
        issues: list[SchemaIssue] = []
        dimensions = [
            str(item["dimension_id"])
            for item in validated.output["dimension_reviews"]
        ]
        if len(dimensions) != len(set(dimensions)):
            issues.append(
                SchemaIssue(
                    "$.dimension_reviews",
                    "八个审阅维度不得重复",
                )
            )
        if set(dimensions) != set(DEEP_REVIEW_DIMENSIONS):
            missing = sorted(set(DEEP_REVIEW_DIMENSIONS) - set(dimensions))
            unexpected = sorted(set(dimensions) - set(DEEP_REVIEW_DIMENSIONS))
            issues.append(
                SchemaIssue(
                    "$.dimension_reviews",
                    f"必须完整覆盖八维；缺少 {missing}，未知 {unexpected}",
                )
            )
        finding_ids = [
            str(item["finding_id"]) for item in validated.output["findings"]
        ]
        if len(finding_ids) != len(set(finding_ids)):
            issues.append(SchemaIssue("$.findings", "finding_id 不得重复"))
        known_findings = set(finding_ids)
        for index, item in enumerate(validated.output["dimension_reviews"]):
            unknown = sorted(
                set(map(str, item["linked_finding_ids"])) - known_findings
            )
            if unknown:
                issues.append(
                    SchemaIssue(
                        f"$.dimension_reviews[{index}].linked_finding_ids",
                        f"引用了不存在的问题：{unknown}",
                    )
                )
        for index, item in enumerate(validated.output["action_plan"]):
            unknown = sorted(
                set(map(str, item["finding_ids"])) - known_findings
            )
            if unknown:
                issues.append(
                    SchemaIssue(
                        f"$.action_plan[{index}].finding_ids",
                        f"引用了不存在的问题：{unknown}",
                    )
                )
        if issues:
            raise SchemaValidationError(tuple(issues))
        return validated
