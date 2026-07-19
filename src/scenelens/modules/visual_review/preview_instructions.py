from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence


class PreviewEditMode(StrEnum):
    LIGHTING_ONLY = "lighting_only"
    COLOUR_ONLY = "colour_only"
    FOG_ATMOSPHERE_ONLY = "fog_atmosphere_only"


@dataclass(frozen=True)
class PreviewProtectionControls:
    preserve_composition: bool = True
    preserve_geometry: bool = True
    preserve_asset_identity: bool = True
    preserve_regions: tuple[str, ...] = ()


def change_budget_semantics(percent: int) -> str:
    if not 0 <= percent <= 100 or percent % 5:
        raise ValueError("AI change budget must use 5% steps inside 0..100")
    if percent <= 20:
        return "仅允许全局色调、曝光和轻微氛围调整"
    if percent <= 50:
        return "允许灯光、雾、材质响应和焦点强化，几何锁定"
    if percent <= 75:
        return "允许明显局部重照明和次要元素调整"
    return "允许美术方向重解释；高风险，必须显示强警告"


def build_structured_preview_instruction(
    *,
    mode: PreviewEditMode,
    change_budget_percent: int,
    creative_intent: Mapping[str, Any],
    reference_visual_brief: Mapping[str, Any],
    confirmed_tasks: Sequence[Mapping[str, Any]],
    paired_regions: Sequence[Mapping[str, Any]],
    protection: PreviewProtectionControls,
) -> dict[str, Any]:
    semantics = change_budget_semantics(change_budget_percent)
    return {
        "instruction_format": "scenelens.ai_concept_preview",
        "instruction_version": 1,
        "output_type": "AIConceptPreview",
        "edit_mode": mode.value,
        "change_budget": {
            "percent": change_budget_percent,
            "semantics": semantics,
            "mathematical_interpolation": False,
        },
        "creative_intent": dict(creative_intent),
        "reference_visual_brief": dict(reference_visual_brief),
        "confirmed_tasks": [dict(item) for item in confirmed_tasks],
        "paired_regions": [dict(item) for item in paired_regions],
        "protection": {
            **asdict(protection),
            "preserve_regions": list(protection.preserve_regions),
        },
        "prohibitions": [
            "不得把输出表示为真实 UE 截图 Version",
            "不得改动被保护区域",
            "不得从 Markdown 或建议条数推断改动强度",
        ],
    }
