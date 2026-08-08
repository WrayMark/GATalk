from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
import re
from typing import Any, Mapping

from scenelens.core.schema_validation import require_valid_json_schema
from scenelens.core.workspaces import ReviewerDescriptor
from scenelens.providers.contracts import ProviderImage, VisionReviewRequest

from . import MODULE_ID


STUDY_DIMENSIONS = (
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

EVALUATION_STATUS_LABELS = {
    "strong": "表现突出",
    "effective_with_tradeoffs": "有效但有取舍",
    "mixed": "效果混合",
    "limited": "作用有限",
    "insufficient_evidence": "证据不足",
}

_INTERNAL_TEXT_FIELDS = {
    "schema_version",
    "reviewer_id",
    "dimension_id",
    "evaluation_status",
    "annotation_id",
    "evidence_type",
    "linked_dimensions",
    "item_id",
}
_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")
_COMMON_TRADITIONAL_CHARS = set(
    "體這與為會個來時裏裡後於從還進過讓顯壓質學術風場畫圖構層"
    "邊遠點線鏡頭觀覺應關敘節陰陽顏實將種說較區間難轉優勢問題"
)


class ArtworkStudyLanguageError(ValueError):
    def __init__(self, paths: tuple[str, ...]) -> None:
        self.paths = paths
        super().__init__(
            "作品研究结果没有完整使用简体中文，需执行一次中文规范化。"
        )

    def to_user_message(self) -> str:
        return (
            "AI 第二次返回仍未完整使用简体中文。"
            "请稍后重试或更换模型。"
        )


def evaluation_status_label(value: object) -> str:
    return EVALUATION_STATUS_LABELS.get(str(value), "未知状态")


def non_simplified_chinese_paths(
    output: Mapping[str, Any],
) -> tuple[str, ...]:
    issues: list[str] = []

    def visit(value: Any, path: str, field: str | None = None) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                visit(item, f"{path}.{key}", str(key))
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]", field)
            return
        if not isinstance(value, str) or field in _INTERNAL_TEXT_FIELDS:
            return
        text = value.strip()
        if not text:
            return
        cjk_count = len(_CJK_PATTERN.findall(text))
        latin_count = len(_LATIN_PATTERN.findall(text))
        contains_traditional = any(
            character in _COMMON_TRADITIONAL_CHARS for character in text
        )
        mostly_english = (
            (cjk_count == 0 and latin_count >= 4)
            or latin_count > max(24, cjk_count * 3)
        )
        if contains_traditional or mostly_english:
            issues.append(path)

    visit(output, "$")
    return tuple(issues)


def is_simplified_chinese_review(output: Mapping[str, Any]) -> bool:
    return not non_simplified_chinese_paths(output)


@dataclass(frozen=True)
class ArtworkStudyContext:
    study_id: str
    title: str
    work_type: str
    study_goal: str
    known_context: str
    image_metadata: Mapping[str, Any]
    local_evidence: Mapping[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "study": {
                "study_id": self.study_id,
                "title": self.title,
                "work_type": self.work_type,
                "study_goal": self.study_goal,
                "known_context": self.known_context,
            },
            "image_metadata": dict(self.image_metadata),
            "local_evidence": dict(self.local_evidence),
            "method_contract": {
                "sequence": [
                    "close_description",
                    "formal_relationships",
                    "visual_effect",
                    "interpretation",
                    "evaluation",
                    "transferable_learning",
                ],
                "source_types": [
                    "visible_image_evidence",
                    "local_measurement",
                    "expert_inference",
                    "contextual_hypothesis",
                ],
                "evaluation_rule": (
                    "不得以风格偏好替代评价；先说明作品试图解决的问题，"
                    "再判断视觉选择是否有效及其代价。"
                ),
            },
        }


def load_artwork_study_schema() -> Mapping[str, Any]:
    resource = files(
        "scenelens.modules.artwork_study.schemas"
    ).joinpath("artwork_study_review.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


class ArtworkMasterStudyReview:
    max_output_tokens = 32768
    system_instruction = (
        "你是一位严谨、博学、善于教学的资深 CG 主美与视觉开发导师。"
        "你的任务是带一位有专业基础的美术从业者逐层研究单张作品，而不是"
        "生成泛泛点评、夸奖清单或复刻教程。先做不带解释的近距离描述，再分析"
        "视觉元素之间的关系、产生的观看效果、可能的叙事或设计意图，最后评价"
        "其有效性、取舍和可迁移规律。必须完整覆盖十二个维度，但维度之间不能"
        "彼此孤立：用 causal_chains 说明构图、明度、色彩、光、空间、形状、"
        "边缘、材质、叙事与情绪怎样互相作用。抽象分析必须落回具体画面位置，"
        "具象内容必须说明它对视觉组织和叙事的作用。"
        "区分 visible_image_evidence、local_measurement、expert_inference 和"
        "contextual_hypothesis；只有 payload 中出现的数值才可称为测量。"
        "本地九宫格 attention_proxy 只是反差/边缘/彩度代理，绝不能声称为"
        "真实眼动或语义显著性。不得伪造作者、项目背景、焦距、Lux、EV、材质"
        "节点或制作过程。看不清或无法从单图证明时必须写入 uncertainty。"
        "评价要说明何种目标下有效、代价是什么，不使用总分。语言面向美术"
        "从业者，可以准确使用专业术语，但每个关键术语要由画面证据解释。"
        "复刻与制作步骤只占很低比例；transferable_principles 侧重学习规律。"
        "深度来自证据和关系，不来自冗长重复：每个维度的单个文字字段控制在"
        "180 个简体中文字符以内；证据、关系和学习点每项控制在 100 字以内；"
        "避免同一观察在多个字段重复。"
        "【语言硬性要求】除 JSON 键名、固定 ID、枚举值、十六进制颜色、数值和"
        "Oklab、CG、UE5、P10 等必要技术标识外，所有可见自然语言字段必须使用"
        "中国大陆通行的简体中文。不得输出英文句子、英文段落或繁体中文。"
        "即使图片含英文文字，也必须用简体中文解释其作用。"
        "只输出符合给定 JSON Schema 的 JSON。"
    )
    descriptor = ReviewerDescriptor(
        module_id=MODULE_ID,
        reviewer_id="artwork_master_study",
        display_name="CG 主美作品深度研究",
        version="1.2.0",
        supported_inputs=(
            "single_artwork_image",
            "study_goal",
            "known_context",
            "image_metadata",
            "local_measurements",
            "spatial_evidence_grid",
        ),
        output_schema=load_artwork_study_schema(),
    )

    @property
    def output_schema(self) -> Mapping[str, Any]:
        return self.descriptor.output_schema

    def create_request(
        self,
        context: ArtworkStudyContext,
        images: tuple[ProviderImage, ...],
        *,
        model_id: str | None = None,
        user_initiated: bool = False,
        disclosure_confirmed: bool = False,
    ) -> VisionReviewRequest:
        if len(images) != 1 or images[0].role != "artwork":
            raise ValueError("作品研究需要且只接受一张 artwork 图片。")
        return VisionReviewRequest(
            system_instruction=self.system_instruction,
            payload=context.to_payload(),
            images=images,
            output_schema=self.output_schema,
            model_id=model_id,
            user_initiated=user_initiated,
            disclosure_confirmed=disclosure_confirmed,
            max_output_tokens=self.max_output_tokens,
            timeout_seconds=180.0,
        )

    def validate_output(self, output: Mapping[str, Any]) -> dict[str, Any]:
        require_valid_json_schema(output, self.output_schema)
        dimensions = [
            str(item["dimension_id"])
            for item in output["dimension_studies"]
        ]
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("作品研究维度不得重复。")
        if set(dimensions) != set(STUDY_DIMENSIONS):
            missing = sorted(set(STUDY_DIMENSIONS) - set(dimensions))
            unexpected = sorted(set(dimensions) - set(STUDY_DIMENSIONS))
            raise ValueError(
                f"作品研究必须完整覆盖十二维；缺少 {missing}，未知 {unexpected}。"
            )
        language_issues = non_simplified_chinese_paths(output)
        if language_issues:
            raise ArtworkStudyLanguageError(language_issues)
        return dict(output)

    def create_language_normalization_request(
        self,
        output: Mapping[str, Any],
        *,
        model_id: str | None = None,
        user_initiated: bool = False,
        disclosure_confirmed: bool = False,
    ) -> VisionReviewRequest:
        return VisionReviewRequest(
            system_instruction=(
                "你是 GATalk 的简体中文规范化校对器。输入是一份已经完成的"
                "作品研究 JSON。只把其中面向用户的自然语言值转换为中国大陆"
                "通行的简体中文；不得增加、删除、概括或改写美术结论。必须原样"
                "保留全部 JSON 键、数组顺序、数值、坐标、可信度、颜色、"
                "schema_version、reviewer_id、dimension_id、evaluation_status、"
                "evidence_type、annotation_id 和 linked_dimensions。Oklab、CG、"
                "UE5、P10 等必要技术标识可以保留，但解释必须是简体中文。"
                "只输出符合给定 JSON Schema 的完整 JSON。"
            ),
            payload={
                "task": "convert_human_readable_values_to_zh_cn",
                "source_output": dict(output),
            },
            images=(),
            output_schema=self.output_schema,
            model_id=model_id,
            user_initiated=user_initiated,
            disclosure_confirmed=disclosure_confirmed,
            max_output_tokens=self.max_output_tokens,
            timeout_seconds=180.0,
        )


def format_artwork_review_report(output: Mapping[str, Any]) -> str:
    lines = [
        str(output.get("executive_thesis", "")),
        "",
        "逐层拆解",
    ]
    labels = {
        "composition": "构图组织",
        "visual_hierarchy": "视觉层级",
        "value_structure": "明度结构",
        "colour_design": "色彩设计",
        "lighting": "光影组织",
        "spatial_depth": "空间层次",
        "shape_language": "形状语言",
        "edge_detail_control": "边缘与细节控制",
        "material_surface": "材质与表面",
        "environment_storytelling": "环境叙事",
        "style_technique": "风格与技法",
        "emotional_impact": "情绪作用",
    }
    for item in output.get("dimension_studies", []):
        lines.extend(
            [
                "",
                labels.get(str(item.get("dimension_id")), str(item.get("dimension_id"))),
                f"观察：{item.get('observation', '')}",
                f"证据：{'；'.join(item.get('visual_evidence', []))}",
                f"解释：{item.get('interpretation', '')}",
                f"作用：{item.get('effect_on_viewer', '')}",
                f"评价：{item.get('evaluation', '')}",
                f"学习点：{'；'.join(item.get('learning_points', []))}",
                f"不确定性：{item.get('uncertainty', '')}",
            ]
        )
    lines.extend(["", "跨维度因果链"])
    for item in output.get("causal_chains", []):
        lines.append(
            f"{item.get('cause', '')} → {item.get('mechanism', '')} → "
            f"{item.get('effect', '')}"
        )
    lines.extend(["", "可迁移规律"])
    for item in output.get("transferable_principles", []):
        lines.append(f"• {item}")
    lines.extend(["", "继续观察的问题"])
    for item in output.get("study_questions", []):
        lines.append(f"• {item}")
    return "\n".join(lines).strip()
