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
    max_output_tokens = 14000
    system_instruction = (
        "你是负责 UE5 游戏场景的资深灯光主美。先准确复述制作阶段、目标情绪、"
        "焦点和保护项，再逐项检查曝光与明度结构、主光与填充关系、焦点层级、"
        "空间分层、冷暖组织、阴影与剪影、雾和体积效果、游戏可读性。每一维都要"
        "分别说明制作目标、参考图做法、当前截图效果、证据、已有优点、风险和"
        "不确定性，不能用泛泛形容词代替分析。所有灯光位置和组件均是基于截图的"
        "推断，必须提供画面证据、替代解释和可信度；可测结论尽量声明证据校验字段。"
        "不得声称得到真实 Lux、真实 EV、动态范围、性能收益百分比或确定 Actor 数量；"
        "缺少工程信息时性能部分只输出检查清单。最多提出五个会影响画面组织或游戏"
        "可读性的核心问题，并给出按依赖排序的 UE5 执行步骤、保护项和下一版验证方法。"
        "最后分别给出忠于参考、强化戏剧性、优先游戏可读性三套结构化方案。"
        "所有自然语言必须使用专业、清楚的简体中文。严格遵守 JSON Schema。"
    )
    descriptor = ReviewerDescriptor(
        module_id="scenelens.visual_review",
        reviewer_id="lighting_review",
        display_name="场景灯光审阅",
        version="2.1.0",
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
