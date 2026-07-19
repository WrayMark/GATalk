import pytest

from scenelens.modules.visual_review.preview_instructions import (
    PreviewEditMode,
    PreviewProtectionControls,
    build_structured_preview_instruction,
    change_budget_semantics,
)


def test_ai_change_budget_has_explicit_non_interpolation_semantics() -> None:
    instruction = build_structured_preview_instruction(
        mode=PreviewEditMode.LIGHTING_ONLY,
        change_budget_percent=50,
        creative_intent={"目标情绪": "神秘"},
        reference_visual_brief={"主光方向": "左后"},
        confirmed_tasks=({"title": "强化入口焦点"},),
        paired_regions=(),
        protection=PreviewProtectionControls(
            preserve_regions=("钟楼",),
        ),
    )
    assert instruction["output_type"] == "AIConceptPreview"
    assert (
        instruction["change_budget"]["mathematical_interpolation"]
        is False
    )
    assert instruction["protection"]["preserve_geometry"] is True


def test_change_budget_requires_five_percent_steps_and_warns_high() -> None:
    assert "高风险" in change_budget_semantics(100)
    with pytest.raises(ValueError, match="5%"):
        change_budget_semantics(23)
