from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from typing import Any, Mapping

from scenelens.core.schema_validation import require_valid_json_schema
from scenelens.core.workspaces import ReviewerDescriptor
from scenelens.providers.contracts import ProviderImage, VisionReviewRequest

from . import MODULE_ID


def load_asset_breakdown_schema() -> Mapping[str, Any]:
    resource = files(
        "scenelens.modules.asset_breakdown.schemas"
    ).joinpath("asset_breakdown_review.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class AssetBreakdownContext:
    project_id: str
    title: str
    scene_type: str
    scene_focus: tuple[str, ...]
    production_goal: str
    image_metadata: Mapping[str, Any]
    supplemental_references: tuple[Mapping[str, Any], ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "project": {
                "project_id": self.project_id,
                "title": self.title,
                "scene_type": self.scene_type,
                "scene_specific_focus": list(self.scene_focus),
                "production_goal": self.production_goal,
            },
            "main_image_metadata": dict(self.image_metadata),
            "supplemental_references": [
                dict(item) for item in self.supplemental_references
            ],
            "coordinate_contract": {
                "space": "EXIF-corrected main image",
                "format": "[x,y,width,height]",
                "range": "0..1",
                "rule": "框住原画中直接可见的像素证据，不含想象中的背面。",
            },
            "source_contract": {
                "visible_evidence": "可直接从原画指出的形状、位置、重复和材质线索",
                "ai_inference": "资产类别、模块边界、复用关系和被遮挡结构等推断",
                "forbidden": [
                    "把不可见背面写成确定事实",
                    "把背景绘制元素强行当成三维模型",
                    "用灯光色块冒充可制作几何",
                ],
            },
        }


class AssetBreakdownReview:
    max_output_tokens = 32768
    system_instruction = (
        "你是资深游戏环境主美、资产规划师和技术美术。你的任务不是做普通"
        "图像描述，而是把复杂场景原画转换为可校正、可追溯的生产资产清单。"
        "先理解空间层级与场景类型，再区分英雄资产、模块套件、重复实例、"
        "道具组合、植被物种与群落、地形、材质、贴花、灯光特效代理和仅作"
        "画面背景的元素。建筑优先识别立面、墙段、柱、窗、门、屋顶、转角、"
        "收边和变体；道具区分独立物件、组合和重复；植被区分物种、尺度层级"
        "和群落；地表区分几何、可平铺材质、混合层和贴花。"
        "每个资产给出主图中的归一化矩形，只框直接可见区域。visible_evidence"
        "只写原画可核对的证据；类别、模块边界、复用和不可见结构写入"
        "inferred_details 或 uncertainty，并用 ai_inference 标记。不要猜测"
        "不可见背面、精确尺寸、拓扑、材质节点、UE Actor 数量或性能收益。"
        "同一对象不要在父级与零件级重复计数：层级用 parent_asset_id 和"
        "level 表示。asset_id 使用简短稳定的 snake_case ID，引用必须存在。"
        "最多列出 48 个真正影响制作规划的资产，不把每块砖或每片叶子拆成"
        "独立资产。每个文字字段控制在 120 个简体中文字符以内，避免重复。"
        "所有自然语言必须是简体中文；只输出符合 JSON Schema 的 JSON。"
    )
    descriptor = ReviewerDescriptor(
        module_id=MODULE_ID,
        reviewer_id="asset_breakdown_review",
        display_name="游戏场景资产拆分",
        version="1.0.0",
        supported_inputs=(
            "main_concept_image",
            "supplemental_reference_images",
            "scene_profile",
            "production_goal",
        ),
        output_schema=load_asset_breakdown_schema(),
    )

    @property
    def output_schema(self) -> Mapping[str, Any]:
        return self.descriptor.output_schema

    def create_request(
        self,
        context: AssetBreakdownContext,
        images: tuple[ProviderImage, ...],
        *,
        model_id: str | None = None,
        user_initiated: bool = False,
        disclosure_confirmed: bool = False,
    ) -> VisionReviewRequest:
        if not images or images[0].role != "main_concept":
            raise ValueError("资产拆分需要一张 main_concept 主原画。")
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
        asset_ids = [str(item["asset_id"]) for item in output["assets"]]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("AI 资产清单包含重复 asset_id。")
        known = set(asset_ids)
        for index, item in enumerate(output["assets"]):
            parent = str(item["parent_asset_id"])
            if parent and parent not in known:
                raise ValueError(
                    f"assets[{index}].parent_asset_id 引用了不存在的资产。"
                )
            x, y, width, height = (
                float(value) for value in item["normalized_rect"]
            )
            if x + width > 1.000001 or y + height > 1.000001:
                raise ValueError(
                    f"assets[{index}].normalized_rect 超出图片范围。"
                )
        for index, relation in enumerate(output["relationships"]):
            if (
                str(relation["source_asset_id"]) not in known
                or str(relation["target_asset_id"]) not in known
            ):
                raise ValueError(
                    f"relationships[{index}] 引用了不存在的资产。"
                )
        return dict(output)


def asset_generation_instruction(
    asset: Mapping[str, Any],
    *,
    output_kind: str,
    scene_type: str,
) -> dict[str, Any]:
    mode_text = {
        "isolated_concept": (
            "生成该资产的独立概念展示图：完整保留正面可见设计语言，"
            "中性背景，清楚展示轮廓和材质分区。"
        ),
        "occlusion_completion": (
            "对被遮挡部分做保守的概念补全。直接可见部分必须保持；"
            "不可见部分只是设计假设，不得添加无依据的复杂结构。"
        ),
        "presentation": (
            "生成便于资产评审的正交感展示图，包含主视图和少量细节，"
            "保持几何身份，不改成不同资产。"
        ),
    }
    if output_kind not in mode_text:
        raise ValueError("未知的资产生成类型。")
    return {
        "output_type": "AssetConceptArtifact",
        "output_kind": output_kind,
        "scene_type": scene_type,
        "asset": {
            "asset_id": str(asset.get("asset_id", "")),
            "name": str(asset.get("name", "")),
            "category": str(asset.get("category", "")),
            "visible_evidence": str(asset.get("visible_evidence", "")),
            "inferred_details": str(asset.get("inferred_details", "")),
            "uncertainty": str(asset.get("uncertainty", "")),
            "material_notes": str(asset.get("material_notes", "")),
        },
        "instruction": mode_text[output_kind],
        "hard_constraints": [
            "只生成所选资产，不生成完整场景",
            "直接可见部分优先服从输入图片",
            "不可见背面和遮挡补全必须视为概念假设",
            "不要加入文字、水印或无关道具",
        ],
    }

