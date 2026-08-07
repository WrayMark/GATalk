from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from scenelens.core.workspaces import WorkbenchRegistry
from scenelens.modules.asset_breakdown.artifacts import (
    asset_crop_png,
    make_asset_board,
    make_asset_board_pages,
    write_asset_manifest,
)
from scenelens.modules.asset_breakdown.models import (
    AssetItem,
    PromptMessage,
    PromptRevision,
)
from scenelens.modules.asset_breakdown.advisory import (
    AssetBreakdownAdvisoryContext,
    AssetBreakdownAdvisoryReview,
)
from scenelens.modules.asset_breakdown.planning import (
    create_plan_from_preset,
    plan_fingerprint,
    plan_from_ai,
    understanding_from_ai,
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


def test_advisory_separates_scene_understanding_from_user_plan() -> None:
    reviewer = AssetBreakdownAdvisoryReview()
    request = reviewer.create_request(
        AssetBreakdownAdvisoryContext(
            project_id="advisory",
            title="山地寺院",
            scene_type="stylized_environment",
            production_goal="规划可复用建筑套件",
            image_metadata={"width": 1920, "height": 1080},
            study_handoff={"study_goal": "理解建筑族和空间层次"},
        ),
        (ProviderImage("main_concept", "image/png", b"image"),),
        user_initiated=True,
        disclosure_confirmed=True,
    )
    output = reviewer.validate_output(
        MockProvider().review(request, "", CancellationToken()).output
    )
    understanding = understanding_from_ai(
        output["scene_understanding"],
        source_image_sha256="sha",
        provider_id="mock",
        model_id="mock-vision-v1",
        analyzer_version=reviewer.descriptor.version,
    )
    plans = tuple(
        plan_from_ai(item, understanding_id=understanding.understanding_id)
        for item in output["recommended_plans"]
    )
    assert understanding.asset_families
    assert len(plans) == 2
    assert plans[0].plan_id != plans[1].plan_id
    assert plans[0].category_depths != plans[1].category_depths
    assert all(item.status == "draft" for item in plans)


def test_breakdown_context_carries_selected_plan_without_local_path() -> None:
    plan = create_plan_from_preset("detail_components")
    context = AssetBreakdownContext(
        project_id="p1",
        title="细节拆分",
        scene_type="interior",
        scene_focus=(),
        production_goal="拆门窗与框架",
        image_metadata={"width": 640, "height": 360},
        supplemental_references=(),
        breakdown_plan=plan.to_dict(),
        study_handoff={"study_goal": "理解建筑语言"},
    )
    payload = context.to_payload()
    assert payload["breakdown_plan"]["category_depths"]["building"] == 4
    assert payload["study_handoff"] == {"study_goal": "理解建筑语言"}
    assert "source_project_path" not in str(payload)


def test_plan_fingerprint_changes_only_for_production_relevant_edits() -> None:
    plan = create_plan_from_preset("production_kit")
    renamed_timestamp = replace(plan, updated_at="later", status="confirmed")
    changed_depth = replace(
        plan,
        category_depths={**plan.category_depths, "building": 4},
    )
    assert plan_fingerprint(plan) == plan_fingerprint(renamed_timestamp)
    assert plan_fingerprint(plan) != plan_fingerprint(changed_depth)


def test_asset_prompt_workshop_supports_initial_and_text_only_refinement() -> None:
    reviewer = AssetPromptWorkshopReview()
    plan = create_plan_from_preset("detail_components")
    context = AssetPromptContext(
        project_id="prompt-project",
        title="赛博街道",
        scene_type="urban_cyberpunk",
        production_goal="整理可复用街景资产",
        notes="保留霓虹招牌和雨夜气氛",
        target_tool="nano_banana",
        image_metadata={"width": 1920, "height": 1080},
        scene_understanding={"summary": "多层街道与重复立面"},
        breakdown_plan=plan.to_dict(),
        study_handoff={"study_goal": "理解建筑层级"},
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
    assert initial.payload["breakdown_plan"]["category_depths"]["building"] == 4
    assert initial.payload["scene_understanding"]["summary"] == (
        "多层街道与重复立面"
    )
    assert initial.payload["study_handoff"]["study_goal"] == "理解建筑层级"

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
    assert {item.reviewer_id for item in registry.reviewers()} == {
        "asset_breakdown_advisory",
        "asset_breakdown_review",
        "asset_prompt_workshop",
    }


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


def test_asset_board_paginates_by_production_group(tmp_path: Path) -> None:
    entries = []
    for index in range(7):
        asset = create_manual_asset(
            name=f"塔楼模块 {index}",
            category="building" if index < 5 else "prop",
            rect=(0.1, 0.1, 0.2, 0.2),
            source_image_id="main",
        )
        asset = replace(
            asset,
            reuse_group="tower" if index < 5 else "street_props",
        )
        path = tmp_path / f"{index}.png"
        Image.new("RGBA", (32, 32), (30, 60, 90, 255)).save(path)
        entries.append((asset, path))
    pages = make_asset_board_pages(
        entries,
        title="模块资产板",
        grouping_strategy="asset_family",
        max_items_per_page=4,
    )
    assert len(pages) == 3
    assert [len(item.asset_ids) for item in pages] == [4, 1, 2]
    assert set().union(*(set(item.asset_ids) for item in pages)) == {
        asset.asset_id for asset, _path in entries
    }
