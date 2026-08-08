from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from typing import Any, Mapping

from scenelens.core.schema_validation import require_valid_json_schema
from scenelens.core.workspaces import ReviewerDescriptor
from scenelens.modules.artwork_study.reviews import non_simplified_chinese_paths
from scenelens.modules.comparative_study import MODULE_ID
from scenelens.providers.contracts import ProviderImage, VisionReviewRequest


def load_comparative_study_schema() -> Mapping[str, Any]:
    resource = files(
        "scenelens.modules.comparative_study.schemas"
    ).joinpath("comparative_study_review.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ComparativeStudyContext:
    study_id: str
    title: str
    research_question: str
    known_context: str
    selected_axes: tuple[str, ...]
    items: tuple[Mapping[str, Any], ...]
    local_comparison: Mapping[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "study": {
                "study_id": self.study_id,
                "title": self.title,
                "research_question": self.research_question,
                "known_context": self.known_context,
                "selected_axes": list(self.selected_axes),
            },
            "works": [dict(item) for item in self.items],
            "local_comparison": dict(self.local_comparison),
            "method_contract": {
                "sequence": [
                    "describe_each_work",
                    "compare_formal_relationships",
                    "explain_visual_effects",
                    "separate_evidence_and_inference",
                    "derive_transferable_principles",
                ],
                "comparison_rule": (
                    "同一比较轴使用相同问题审视全部作品；差异必须说明画面位置、"
                    "视觉作用和适用条件，不把题材偏好写成质量结论。"
                ),
            },
        }


class ComparativeArtworkReview:
    max_output_tokens = 24576
    system_instruction = (
        "你是一位负责高级作品研讨课的资深 CG 主美。对 2 至 6 件作品做严格的"
        "并置研究：先分别概括每件作品采用的核心视觉策略，再沿用户指定的比较轴"
        "逐项比较。每项必须同时写出共同点、差异、画面证据、产生的观看效果、"
        "合理解释和置信度。比较不是排名，不使用总分，不以个人风格偏好代替"
        "判断。只把输入中的数值称为测量；作者意图、制作流程、焦距、灯光参数"
        "和不可见内容若无证据必须标为不确定。可迁移规律应说明适用条件和边界，"
        "避免把表面造型复制当作规律。面向专业美术从业者，准确、简洁、完整使用"
        "中国大陆通行的简体中文。只输出符合给定 JSON Schema 的 JSON。"
    )
    descriptor = ReviewerDescriptor(
        module_id=MODULE_ID,
        reviewer_id="comparative_artwork_study",
        display_name="作品对照研究",
        version="1.0.0",
        supported_inputs=(
            "multiple_artwork_images",
            "research_question",
            "formal_measurements",
            "user_selected_axes",
        ),
        output_schema=load_comparative_study_schema(),
    )

    def create_request(
        self,
        context: ComparativeStudyContext,
        images: tuple[ProviderImage, ...],
        *,
        model_id: str | None = None,
        user_initiated: bool = False,
        disclosure_confirmed: bool = False,
    ) -> VisionReviewRequest:
        if not 2 <= len(images) <= 6:
            raise ValueError("作品对照研究需要 2 至 6 张图片。")
        return VisionReviewRequest(
            system_instruction=self.system_instruction,
            payload=context.to_payload(),
            images=images,
            output_schema=self.descriptor.output_schema,
            model_id=model_id,
            user_initiated=user_initiated,
            disclosure_confirmed=disclosure_confirmed,
            timeout_seconds=240.0,
            max_output_tokens=self.max_output_tokens,
        )

    def validate_output(self, output: Mapping[str, Any]) -> dict[str, Any]:
        require_valid_json_schema(output, self.descriptor.output_schema)
        issues = non_simplified_chinese_paths(output)
        if issues:
            raise ValueError("AI 对照研究未完整使用简体中文，请更换模型后重试。")
        return dict(output)


def format_comparative_review(value: Mapping[str, Any]) -> str:
    lines = [str(value.get("research_thesis", "")), "", "作品策略"]
    for item in value.get("work_profiles", ()):
        lines.append(
            f"{item.get('item_id', '')}：{item.get('core_strategy', '')}\n"
            f"证据：{'；'.join(item.get('visible_evidence', ())) }\n"
            f"不确定性：{item.get('uncertainty', '')}"
        )
    lines.extend(("", "逐轴对照"))
    for item in value.get("axis_comparisons", ()):
        lines.extend(
            (
                f"\n{item.get('axis', '')}",
                f"共同点：{'；'.join(item.get('similarities', ())) or '未发现明确共同点'}",
                f"差异：{'；'.join(item.get('differences', ()))}",
                f"证据：{'；'.join(item.get('evidence', ()))}",
                f"作用：{item.get('visual_effect', '')}",
                f"解释：{item.get('interpretation', '')}",
                f"可信度：{float(item.get('confidence', 0.0)):.2f}",
            )
        )
    lines.extend(("", "跨维度关系"))
    lines.extend(f"• {item}" for item in value.get("cross_axis_findings", ()))
    lines.extend(("", "可迁移规律"))
    lines.extend(f"• {item}" for item in value.get("transferable_principles", ()))
    lines.extend(("", "研究边界"))
    lines.extend(f"• {item}" for item in value.get("limitations", ()))
    lines.extend(("", "下一轮观察问题"))
    lines.extend(f"• {item}" for item in value.get("study_questions", ()))
    return "\n".join(lines).strip()
