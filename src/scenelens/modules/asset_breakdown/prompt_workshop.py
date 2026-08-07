from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
import json
from typing import Any, Mapping, Sequence

from scenelens.core.schema_validation import require_valid_json_schema
from scenelens.core.workspaces import ReviewerDescriptor
from scenelens.providers.contracts import ProviderImage, VisionReviewRequest

from . import MODULE_ID
from .models import PromptMessage, PromptRevision


def load_asset_prompt_schema() -> Mapping[str, Any]:
    resource = files(
        "scenelens.modules.asset_breakdown.schemas"
    ).joinpath("asset_prompt_workshop.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class AssetPromptContext:
    project_id: str
    title: str
    scene_type: str
    production_goal: str
    notes: str
    target_tool: str
    image_metadata: Mapping[str, Any]
    supplemental_references: tuple[Mapping[str, Any], ...] = ()
    scene_understanding: Mapping[str, Any] = field(default_factory=dict)
    breakdown_plan: Mapping[str, Any] = field(default_factory=dict)
    study_handoff: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "project": {
                "project_id": self.project_id,
                "title": self.title,
                "scene_type": self.scene_type,
                "production_goal": self.production_goal,
                "user_notes": self.notes,
            },
            "target_tool": self.target_tool,
            "main_image_metadata": dict(self.image_metadata),
            "supplemental_references": [
                dict(item) for item in self.supplemental_references
            ],
            "scene_understanding": dict(self.scene_understanding),
            "breakdown_plan": dict(self.breakdown_plan),
            "study_handoff": dict(self.study_handoff),
        }


class AssetPromptWorkshopReview:
    max_output_tokens = 20000
    system_instruction = (
        "你是资深游戏环境主美、概念设计师和生成式图像提示语工程师。"
        "你的任务是根据场景原画，为游戏资产拆分和资产展示板生成可直接复制"
        "给其他图像生成工具的提示语，并根据用户反馈继续修订。"
        "先识别原画中可见的建筑、模块构件、道具、植被、地形、材质、贴花、"
        "远景、角色载具和灯光特效代理，再组织成有制作价值的资产组。"
        "若输入包含 breakdown_plan，必须逐项服从类别拆分深度：0 不纳入，"
        "1 只保留场景区域或整体对象，2 拆到完整装配体，3 拆到生产"
        "套件，4 才继续拆分门窗、框架、檐口和装饰组件。"
        "scene_understanding 和 study_handoff 用于说明空间层级、复用关系"
        "与制作目标，但不得替代当前图片证据。"
        "提示语应要求输出整洁的资产拆分展示板：资产彼此分离、轮廓完整、"
        "不裁切、背景中性、设计语言一致、保留原画身份，必要时包含主视图和"
        "少量辅助视图。不要把原画中不可见的背面、内部结构或材质细节写成"
        "确定事实；推测内容必须以保守补全、可选设计或不确定性表达。"
        "prompt_zh 和 prompt_en 都必须是完整可复制的生图指令，而不是摘要。"
        "negative_prompt 写应避免的错误；constraints 写必须保持的边界。"
        "asset_groups 按制作职能列出资产组，并把直接可见证据与不确定内容"
        "分开。若输入 mode=refine，必须以 current_revision 为基线，只按"
        "user_feedback 修改；保留未被要求改变的内容，并在 change_summary"
        "准确说明本次调整。不要讨论 API、不要输出 Markdown 代码围栏。"
        "除 prompt_en 和 prompt_fragment_en 外，所有自然语言使用简体中文。"
        "只输出符合 JSON Schema 的 JSON。"
    )
    descriptor = ReviewerDescriptor(
        module_id=MODULE_ID,
        reviewer_id="asset_prompt_workshop",
        display_name="资产拆分提示语",
        version="1.0.0",
        supported_inputs=(
            "main_concept_image",
            "supplemental_reference_images",
            "project_context",
            "scene_understanding",
            "breakdown_plan",
            "artwork_study_handoff",
            "current_prompt_revision",
            "user_feedback",
        ),
        output_schema=load_asset_prompt_schema(),
    )

    @property
    def output_schema(self) -> Mapping[str, Any]:
        return self.descriptor.output_schema

    def create_request(
        self,
        context: AssetPromptContext,
        images: tuple[ProviderImage, ...],
        *,
        current_revision: PromptRevision | None = None,
        feedback: str = "",
        messages: Sequence[PromptMessage] = (),
        model_id: str | None = None,
        user_initiated: bool = False,
        disclosure_confirmed: bool = False,
    ) -> VisionReviewRequest:
        if current_revision is None:
            if not images or images[0].role != "main_concept":
                raise ValueError("生成提示语初稿需要一张 main_concept 主原画。")
            mode = "initial"
        else:
            if not feedback.strip():
                raise ValueError("继续协商提示语时需要填写修改意见。")
            mode = "refine"
        payload = context.to_payload()
        payload["mode"] = mode
        if current_revision is not None:
            payload["current_revision"] = current_revision.to_dict()
            payload["user_feedback"] = feedback.strip()
            payload["conversation_tail"] = [
                {
                    "role": item.role,
                    "content": item.content[:1200],
                }
                for item in messages[-12:]
            ]
        return VisionReviewRequest(
            system_instruction=self.system_instruction,
            payload=payload,
            images=images,
            output_schema=self.output_schema,
            model_id=model_id,
            user_initiated=user_initiated,
            disclosure_confirmed=disclosure_confirmed,
            timeout_seconds=240.0,
            max_output_tokens=self.max_output_tokens,
        )

    def validate_output(self, output: Mapping[str, Any]) -> dict[str, Any]:
        require_valid_json_schema(output, self.output_schema)
        return dict(output)
