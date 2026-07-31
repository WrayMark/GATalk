from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from scenelens.core.workspaces import WorkbenchRegistry
from scenelens.modules.asset_breakdown.artifacts import (
    asset_crop_png,
    make_asset_board,
    write_asset_manifest,
)
from scenelens.modules.asset_breakdown.models import (
    AssetItem,
    PromptMessage,
    PromptRevision,
)
from scenelens.modules.asset_breakdown.prompt_workshop import (
    AssetPromptContext,
    AssetPromptWorkshopReview,
)
from scenelens.modules.asset_breakdown.reviews import (
    AssetBreakdownContext,
    AssetBreakdownReview,
    asset_generation_instruction,
)
from scenelens.modules.asset_breakdown.service import (
    asset_from_ai,
    create_manual_asset,
    merge_ai_assets,
    merge_assets,
    split_asset,
)
from scenelens.modules.asset_breakdown.workbench import (
    register_asset_breakdown_workbench,
)
from scenelens.providers.contracts import (
    CancellationToken,
    ProviderImage,
)
from scenelens.providers.mock import MockProvider


def _asset(name: str, rect=(0.1, 0.1, 0.3, 0.3)) -> AssetItem:
    return create_manual_asset(
        name=name,
        category="prop",
        rect=rect,
        source_image_id="main",
    )


def test_asset_rect_split_merge_and_user_authority() -> None:
    original = _asset("木箱")
    left, right = split_asset(original)
    assert left.parent_asset_id == original.asset_id
    assert left.normalized_rect[2] == pytest.approx(0.15)
    assert right.normalized_rect[0] == pytest.approx(0.25)
    merged = merge_assets(
        (left, right),
        name="木箱组合",
        category="prop",
    )
    assert merged.normalized_rect == pytest.approx(original.normalized_rect)
    incoming = AssetItem(
        asset_id=original.asset_id,
        name="AI 同 ID",
        category="building",
        semantic_type="",
        normalized_rect=(0.4, 0.4, 0.2, 0.2),
        evidence_kind="ai_inference",
    )
    combined = merge_ai_assets((original,), (incoming,))
    assert combined[0] == original
    assert combined[1].asset_id != original.asset_id


def test_asset_ai_schema_mock_and_generation_instruction() -> None:
    reviewer = AssetBreakdownReview()
    request = reviewer.create_request(
        AssetBreakdownContext(
            project_id="p1",
            title="村庄",
            scene_type="medieval_village",
            scene_focus=("建筑模块套件",),
            production_goal="拆出可复用资产",
            image_metadata={"width": 320, "height": 180},
            supplemental_references=(),
        ),
        (ProviderImage("main_concept", "image/png", b"image"),),
        user_initiated=True,
        disclosure_confirmed=True,
    )
    assert request.max_output_tokens == 32768
    output = MockProvider().review(
        request,
        "",
        CancellationToken(),
    ).output
    validated = reviewer.validate_output(output)
    assert len(validated["assets"]) == 2
    converted = asset_from_ai(
        validated["assets"][0],
        source_image_id="main",
    )
    assert converted.evidence_kind == "ai_inference"
    instruction = asset_generation_instruction(
        converted.to_dict(),
        output_kind="occlusion_completion",
        scene_type="medieval_village",
    )
    assert instruction["output_type"] == "AssetConceptArtifact"
    assert "不可见" in " ".join(instruction["hard_constraints"])


def test_asset_prompt_workshop_supports_initial_and_text_only_refinement() -> None:
    reviewer = AssetPromptWorkshopReview()
    context = AssetPromptContext(
        project_id="prompt-project",
        title="赛博街道",
        scene_type="urban_cyberpunk",
        production_goal="整理可复用街景资产",
        notes="保留霓虹招牌和雨夜气氛",
        target_tool="nano_banana",
        image_metadata={"width": 1920, "height": 1080},
    )
    initial = reviewer.create_request(
        context,
        (ProviderImage("main_concept", "image/png", b"image"),),
        user_initiated=True,
        disclosure_confirmed=True,
    )
    output = reviewer.validate_output(
        MockProvider().review(
            initial,
            "",
            CancellationToken(),
        ).output
    )
    assert output["reviewer_id"] == "asset_prompt_workshop"
    assert output["prompt_zh"]
    assert output["prompt_en"]
    assert output["asset_groups"]

    base = PromptRevision(
        revision_id="base",
        origin="ai",
        title=output["prompt_title"],
        target_tool=output["target_tool"],
        analysis_summary=output["analysis_summary"],
        prompt_zh=output["prompt_zh"],
        prompt_en=output["prompt_en"],
        negative_prompt=output["negative_prompt"],
        constraints=tuple(output["constraints"]),
        asset_groups=tuple(output["asset_groups"]),
        created_at="now",
    )
    refined = reviewer.create_request(
        context,
        (),
        current_revision=base,
        feedback="减少次要道具，强化建筑模块。",
        messages=(
            PromptMessage("m1", "assistant", "已生成初稿。", "now"),
        ),
        user_initiated=True,
        disclosure_confirmed=True,
    )
    assert refined.images == ()
    assert refined.payload["mode"] == "refine"
    assert refined.payload["user_feedback"] == "减少次要道具，强化建筑模块。"
    assert refined.payload["current_revision"]["revision_id"] == "base"


def test_asset_output_repairs_missing_parent_and_invalid_relationship() -> None:
    reviewer = AssetBreakdownReview()
    output = _mock_asset_output(reviewer)
    original = deepcopy(output)
    output["assets"][0]["parent_asset_id"] = "missing_building"
    output["assets"][0]["normalized_rect"] = [0.9, 0.8, 0.4, 0.5]
    output["relationships"].append(
        {
            "source_asset_id": output["assets"][0]["asset_id"],
            "target_asset_id": "missing_prop",
            "relation": "assembled_with",
            "evidence": "AI 返回了无法解析的目标引用",
        }
    )

    normalized, notes = reviewer.normalize_output(output)

    assert normalized["assets"][0]["parent_asset_id"] == ""
    assert sum(normalized["assets"][0]["normalized_rect"][::2]) <= 1.000001
    assert sum(normalized["assets"][0]["normalized_rect"][1::2]) <= 1.000001
    assert all(
        relation["target_asset_id"] != "missing_prop"
        for relation in normalized["relationships"]
    )
    assert any("取消不存在的父级引用 1 项" in note for note in notes)
    assert any("裁剪越界区域 1 项" in note for note in notes)
    assert any("移除无效资产关系 1 项" in note for note in notes)
    assert original["assets"][0]["parent_asset_id"] == ""


def test_asset_output_repairs_duplicate_ids_and_parent_cycles() -> None:
    reviewer = AssetBreakdownReview()
    output = _mock_asset_output(reviewer)
    first, second = output["assets"][:2]
    first["asset_id"] = "building_a"
    first["parent_asset_id"] = "building_b"
    second["asset_id"] = "building_b"
    second["parent_asset_id"] = "building_a"
    duplicate = deepcopy(second)
    duplicate["name"] = "建筑 B 变体"
    output["assets"].append(duplicate)

    normalized, notes = reviewer.normalize_output(output)
    ids = [asset["asset_id"] for asset in normalized["assets"]]

    assert len(ids) == len(set(ids))
    assert "building_b_2" in ids
    assert any(
        not asset["parent_asset_id"]
        for asset in normalized["assets"]
        if asset["asset_id"] in {"building_a", "building_b"}
    )
    assert any("重命名重复资产 ID 1 项" in note for note in notes)
    assert any("断开循环父级 1 项" in note for note in notes)


def test_asset_workbench_registration() -> None:
    registry = WorkbenchRegistry()
    register_asset_breakdown_workbench(registry)
    assert registry.workspaces()[0].workspace_id == "asset_breakdown"
    assert (
        registry.reviewers()[0].reviewer_id
        == "asset_breakdown_review"
    )
    assert registry.reviewers()[1].reviewer_id == "asset_prompt_workshop"


def _mock_asset_output(reviewer: AssetBreakdownReview) -> dict:
    request = reviewer.create_request(
        AssetBreakdownContext(
            project_id="repair",
            title="结构修复",
            scene_type="general_environment",
            scene_focus=(),
            production_goal="验证 AI 引用修复",
            image_metadata={"width": 320, "height": 180},
            supplemental_references=(),
        ),
        (ProviderImage("main_concept", "image/png", b"image"),),
        user_initiated=True,
        disclosure_confirmed=True,
    )
    return deepcopy(
        dict(
            MockProvider().review(
                request,
                "",
                CancellationToken(),
            ).output
        )
    )


def test_crop_board_and_manifest_are_exportable(tmp_path: Path) -> None:
    rgb = np.full((120, 180, 3), (30, 45, 60), dtype=np.uint8)
    rgb[25:95, 40:140] = (190, 120, 65)
    asset = _asset("中文 道具", (0.2, 0.15, 0.65, 0.7))
    mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    mask[25:95, 40:140] = 255
    crop = asset_crop_png(rgb, asset, mask)
    crop_path = tmp_path / "crop.png"
    crop_path.write_bytes(crop)
    with Image.open(BytesIO(crop)) as image:
        assert image.mode == "RGBA"
        assert image.width > 0
    board = make_asset_board(
        [(asset, crop_path)],
        title="中文资产展示板",
    )
    board_path = tmp_path / "board.png"
    board_path.write_bytes(board)
    with Image.open(board_path) as image:
        assert image.size[0] >= 420
    manifest = write_asset_manifest(
        tmp_path / "asset_manifest.json",
        project={"title": "中文项目"},
        assets=(asset,),
        generations=(),
    )
    assert "中文 道具" in manifest.read_text(encoding="utf-8")
