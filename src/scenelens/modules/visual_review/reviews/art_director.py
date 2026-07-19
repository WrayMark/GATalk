from __future__ import annotations

from scenelens.core.workspaces import ReviewerDescriptor

from .base import StructuredVisionReviewer, load_review_schema


class ArtDirectorReview(StructuredVisionReviewer):
    schema_filename = "art_director_review.schema.json"
    system_instruction = (
        "你是游戏场景主美审阅器。只根据制作意图、参考视觉简报、"
        "提供的图片与测量证据输出 JSON。最多提出五个会影响目标的核心问题；"
        "区分观察、测量和推断，指出反证与不确定性。不得输出泛化总分，"
        "不得虚构图片之外的 UE 工程设置。严格遵守给定 JSON Schema。"
    )
    descriptor = ReviewerDescriptor(
        module_id="scenelens.visual_review",
        reviewer_id="art_director_review",
        display_name="主美专项审阅",
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
            "quality_gates",
        ),
        output_schema=load_review_schema(
            "art_director_review.schema.json"
        ),
    )
