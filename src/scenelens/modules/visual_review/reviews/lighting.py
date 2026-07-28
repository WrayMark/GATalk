from __future__ import annotations

from scenelens.core.workspaces import ReviewerDescriptor
from scenelens.core.schema_validation import (
    SchemaIssue,
    SchemaValidationError,
)

from .base import (
    StructuredVisionReviewer,
    ValidatedReview,
    load_review_schema,
)


class LightingReview(StructuredVisionReviewer):
    schema_filename = "lighting_review.schema.json"
    max_output_tokens = 8000
    system_instruction = (
        "你是 UE5 游戏场景灯光审片器。所有灯光位置和组件均是基于截图的"
        "推断，必须提供画面证据、替代解释和可信度。不得声称得到真实 Lux、"
        "真实 EV、动态范围、性能收益百分比或确定 Actor 数量；缺少工程信息时"
        "性能部分只输出检查清单。最多提出五个核心问题，并分别给出忠于参考、"
        "强化戏剧性、优先游戏可读性三套结构化方案。严格遵守 JSON Schema。"
    )
    descriptor = ReviewerDescriptor(
        module_id="scenelens.visual_review",
        reviewer_id="lighting_review",
        display_name="灯光专项审阅",
        version="1.0.0",
        supported_inputs=(
            "creative_intent",
            "reference_visual_brief",
            "reference_image",
            "current_image",
            "global_measurements",
            "paired_region_measurements",
            "version_history",
            "locked_goals",
            "production_context",
        ),
        output_schema=load_review_schema("lighting_review.schema.json"),
    )

    def validate_output(self, output) -> ValidatedReview:
        validated = super().validate_output(output)
        strategies = {
            str(item["strategy"])
            for item in validated.output["target_schemes"]
        }
        expected = {
            "faithful_to_reference",
            "heightened_drama",
            "gameplay_readability",
        }
        if strategies != expected:
            raise SchemaValidationError(
                (
                    SchemaIssue(
                        "$.target_schemes",
                        "必须各包含一套忠于参考、强化戏剧性和优先游戏可读性方案",
                    ),
                )
            )
        return validated
