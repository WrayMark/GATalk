from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
import json
from typing import Any, Mapping

from scenelens.core.schema_validation import require_valid_json_schema
from scenelens.core.workspaces import ReviewerDescriptor
from scenelens.providers.contracts import ProviderImage, VisionReviewRequest

from . import MODULE_ID


def load_asset_breakdown_advisory_schema() -> Mapping[str, Any]:
    resource = files(
        "scenelens.modules.asset_breakdown.schemas"
    ).joinpath("asset_breakdown_advisory.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class AssetBreakdownAdvisoryContext:
    project_id: str
    title: str
    scene_type: str
    production_goal: str
    image_metadata: Mapping[str, Any]
    scene_focus: tuple[str, ...] = ()
    supplemental_references: tuple[Mapping[str, Any], ...] = ()
    study_handoff: Mapping[str, Any] = field(default_factory=dict)
    user_corrections: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "project": {
                "project_id": self.project_id,
                "title": self.title,
                "scene_type": self.scene_type,
                "production_goal": self.production_goal,
                "scene_focus": list(self.scene_focus),
            },
            "image_metadata": dict(self.image_metadata),
            "supplemental_references": [
                dict(item) for item in self.supplemental_references
            ],
            "study_handoff": dict(self.study_handoff),
            "user_corrections": self.user_corrections,
            "task_contract": {
                "first": "先理解场景、空间组织和可能的生产系统。",
                "second": "再给出不同目的的拆分方案，不直接产出资产清单。",
                "depth_scale": {
                    "0": "不纳入",
                    "1": "场景区域或完整对象",
                    "2": "完整建筑、装配体、群落或岩组",
                    "3": "可复用生产套件、结构段、物种或材质系统",
                    "4": "门窗、框架、檐口、栏杆、装饰与控制变体",
                },
            },
        }


class AssetBreakdownAdvisoryReview:
    max_output_tokens = 16384
    system_instruction = (
        "你是资深游戏环境主美、环境资产规划师与技术美术。先判断原画属于何种"
        "场景原型、空间如何组织、哪些元素是完整装配体、哪些具有复用信号，"
        "再提出二至四套目的不同的拆分方案。不要把任务退化成通用物体检测。"
        "建筑场景关注区域、建筑群、完整建筑、结构模块、重复组件、材质和变体；"
        "自然场景关注地形形态与材质层、岩组、植被物种、大小变体、群落和地被；"
        "室内、工业、风格化和混合场景使用各自生产逻辑。只把画面可核对内容写成"
        "可见证据；背面、内部结构、尺寸、拼接方式和不可见细节必须列为推断或不确定性。"
        "作品研究交接内容是辅助上下文，不得凌驾于当前图像证据；用户修订优先。"
        "拆分深度按类别分别给出，避免用一个全局粗细等级误导复杂场景。"
        "所有自然语言必须是简体中文，只输出符合 JSON Schema 的 JSON。"
    )
    descriptor = ReviewerDescriptor(
        module_id=MODULE_ID,
        reviewer_id="asset_breakdown_advisory",
        display_name="场景理解与拆分建议",
        version="1.0.0",
        supported_inputs=(
            "main_concept_image",
            "supplemental_reference_images",
            "artwork_study_handoff",
            "production_goal",
        ),
        output_schema=load_asset_breakdown_advisory_schema(),
    )

    @property
    def output_schema(self) -> Mapping[str, Any]:
        return self.descriptor.output_schema

    def create_request(
        self,
        context: AssetBreakdownAdvisoryContext,
        images: tuple[ProviderImage, ...],
        *,
        model_id: str | None = None,
        user_initiated: bool = False,
        disclosure_confirmed: bool = False,
    ) -> VisionReviewRequest:
        if not images or images[0].role != "main_concept":
            raise ValueError("场景理解需要一张 main_concept 主原画。")
        return VisionReviewRequest(
            system_instruction=self.system_instruction,
            payload=context.to_payload(),
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
