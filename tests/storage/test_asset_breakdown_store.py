from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from PIL import Image
import pytest

from scenelens.modules.asset_breakdown.models import (
    AssetPromptSession,
    AutomaticAssetRun,
    GenerationRecord,
    PromptMessage,
    PromptRevision,
    StudyHandoffSnapshot,
)
from scenelens.modules.asset_breakdown.planning import (
    create_plan_from_preset,
)
from scenelens.modules.asset_breakdown.service import create_manual_asset
from scenelens.modules.asset_breakdown.storage import AssetBreakdownStore
from scenelens.storage.errors import ProjectLockedError
from scenelens.storage.project_store import utc_now


def _image(path: Path, colour: tuple[int, int, int]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (96, 64), colour).save(path)
    return path.read_bytes()


def test_asset_project_preserves_bytes_and_restores_edits(
    tmp_path: Path,
) -> None:
    source = tmp_path / "输入 图片" / "中世纪村庄.png"
    original = _image(source, (90, 120, 45))
    root = tmp_path / "中文 用户" / "村庄 资产.scenelens-assets"
    store = AssetBreakdownStore.create(root, "中世纪村庄")
    main = store.import_image(source, "main")
    assert store.image_path(main).read_bytes() == original
    asset = create_manual_asset(
        name="木制摊位",
        category="prop",
        rect=(0.1, 0.2, 0.35, 0.45),
        source_image_id=main.image_id,
    )
    store.add_or_replace_asset(asset)
    store.state = replace(
        store.state,
        scene_type="medieval_village",
        production_goal="拆出复用模块",
        selected_asset_id=asset.asset_id,
    )
    store.save()
    store.append_generation(
        GenerationRecord(
            generation_id="g1",
            asset_id=asset.asset_id,
            output_kind="isolated_concept",
            source_image_sha256=main.sha256,
            source_rect=asset.normalized_rect,
            provider_id="mock",
            model_id="mock-image-v1",
            parameters={"preserve_visible": True},
            relative_path="artifacts/generated/g1.png",
            status="completed",
            created_at=utc_now(),
        )
    )
    store.close()

    reopened = AssetBreakdownStore.open(root)
    assert reopened.state.title == "中世纪村庄"
    assert reopened.state.scene_type == "medieval_village"
    assert reopened.state.assets[0].name == "木制摊位"
    assert reopened.state.generations[0].source_image_sha256 == main.sha256
    assert source.read_bytes() == original
    reopened.close()


def test_asset_project_uses_os_write_lock(tmp_path: Path) -> None:
    root = tmp_path / "locked.scenelens-assets"
    first = AssetBreakdownStore.create(root, "锁测试")
    with pytest.raises(ProjectLockedError):
        AssetBreakdownStore.open(root)
    first.close()
    reopened = AssetBreakdownStore.open(root)
    reopened.close()


def test_replacing_main_clears_derived_records_not_source_files(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    first_bytes = _image(first_path, (10, 20, 30))
    second_bytes = _image(second_path, (80, 90, 100))
    store = AssetBreakdownStore.create(
        tmp_path / "replace.scenelens-assets",
        "替换",
    )
    first = store.import_image(first_path, "main")
    store.add_or_replace_asset(
        create_manual_asset(
            name="资产",
            category="prop",
            rect=(0.1, 0.1, 0.3, 0.3),
            source_image_id=first.image_id,
        )
    )
    store.import_image(second_path, "main")
    assert not store.state.assets
    assert first_path.read_bytes() == first_bytes
    assert second_path.read_bytes() == second_bytes
    store.close()


def test_import_records_exif_corrected_working_dimensions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (40, 80), (60, 70, 80))
    exif = Image.Exif()
    exif[274] = 6
    image.save(source, exif=exif)
    store = AssetBreakdownStore.create(
        tmp_path / "exif.scenelens-assets",
        "EXIF",
    )
    imported = store.import_image(source, "main")
    assert (imported.width, imported.height) == (80, 40)
    assert store.image_path(imported).read_bytes() == source.read_bytes()
    store.close()


def test_automatic_runs_are_independent_and_restore(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.png"
    _image(source, (10, 20, 30))
    root = tmp_path / "automatic.scenelens-assets"
    store = AssetBreakdownStore.create(root, "自动资产板")
    main = store.import_image(source, "main")
    store.append_automatic_run(
        AutomaticAssetRun(
            run_id="auto-1",
            status="completed",
            source_image_sha256=main.sha256,
            vision_provider_id="mock",
            vision_model_id="mock-vision-v1",
            image_provider_id="mock",
            image_model_id="mock-image-v1",
            output_kind="isolated_concept",
            asset_limit=12,
            board_relative_path=(
                "artifacts/automatic/auto-1/asset_board.png"
            ),
            created_at=utc_now(),
        )
    )
    assert not store.state.assets
    store.close()
    reopened = AssetBreakdownStore.open(root)
    assert reopened.state.automatic_runs[0].run_id == "auto-1"
    assert not reopened.state.assets
    reopened.close()


def test_v3_asset_project_is_backed_up_before_v4_migration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "migrate.scenelens-assets"
    store = AssetBreakdownStore.create(root, "迁移")
    store.close()
    entry = root / "asset_project.json"
    payload = json.loads(entry.read_text(encoding="utf-8"))
    payload["format_version"] = 3
    payload["module_schema_version"] = 3
    payload["state"].pop("breakdown_plans", None)
    payload["state"].pop("selected_plan_id", None)
    entry.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    migrated = AssetBreakdownStore.open(root)
    migrated.close()

    updated = json.loads(entry.read_text(encoding="utf-8"))
    assert updated["format_version"] == 4
    assert updated["module_schema_version"] == 4
    assert updated["state"]["breakdown_plans"]
    assert updated["state"]["selected_plan_id"]
    backups = list((root / "backups").glob("asset_project.v3.*.json"))
    assert len(backups) == 1


def test_prompt_sessions_restore_without_touching_source_image(
    tmp_path: Path,
) -> None:
    source = tmp_path / "提示语 原画.png"
    original = _image(source, (30, 80, 120))
    root = tmp_path / "提示语 项目.scenelens-assets"
    store = AssetBreakdownStore.create(root, "提示语项目")
    main = store.import_image(source, "main")
    now = utc_now()
    revision = PromptRevision(
        revision_id="revision-1",
        origin="ai",
        title="建筑资产板",
        target_tool="nano_banana",
        analysis_summary="可见主体建筑和重复灯箱。",
        prompt_zh="生成一张建筑模块资产拆分板。",
        prompt_en="Create a modular architecture asset sheet.",
        negative_prompt="不要裁切。",
        constraints=("保持主体轮廓",),
        asset_groups=(
            {
                "name": "主体建筑",
                "category": "building",
                "visible_evidence": "画面左侧建筑",
                "uncertainty": "背面不可见",
                "prompt_fragment_zh": "主体建筑模块",
                "prompt_fragment_en": "main architecture module",
            },
        ),
        provider_id="mock",
        model_id="mock-vision-v1",
        created_at=now,
    )
    store.add_or_replace_prompt_session(
        AssetPromptSession(
            session_id="session-1",
            title=revision.title,
            source_image_sha256=main.sha256,
            target_tool=revision.target_tool,
            revisions=(revision,),
            messages=(
                PromptMessage(
                    message_id="message-1",
                    role="assistant",
                    content="已生成初稿。",
                    created_at=now,
                ),
            ),
            created_at=now,
            updated_at=now,
        )
    )
    store.close()

    reopened = AssetBreakdownStore.open(root)
    session = reopened.state.prompt_sessions[0]
    assert session.current_revision is not None
    assert session.current_revision.prompt_zh == "生成一张建筑模块资产拆分板。"
    assert reopened.state.selected_prompt_session_id == "session-1"
    assert source.read_bytes() == original
    reopened.close()


def test_study_handoff_and_multiple_breakdown_plans_restore(
    tmp_path: Path,
) -> None:
    source = tmp_path / "研究原画.png"
    original = _image(source, (40, 100, 70))
    root = tmp_path / "交接 项目.scenelens-assets"
    store = AssetBreakdownStore.create(root, "交接项目")
    main = store.import_image(source, "main")
    handoff = StudyHandoffSnapshot(
        handoff_id="handoff-1",
        source_module_id="scenelens.artwork_study",
        source_project_id="study-1",
        source_project_title="寺院研究",
        source_project_path="C:/本地/寺院.scenelens-study",
        source_image_sha256=main.sha256,
        work_type="environment_concept",
        study_goal="理解空间层次",
        known_context="东方幻想",
        personal_notes="中央塔楼是地标。",
        user_adjustments="远景只作为视觉元素。",
        imported_at=utc_now(),
    )
    store.add_or_replace_handoff(handoff)
    assembly = create_plan_from_preset("assembly_set")
    details = create_plan_from_preset("detail_components")
    store.add_or_replace_plan(assembly)
    store.add_or_replace_plan(details)
    store.close()

    reopened = AssetBreakdownStore.open(root)
    assert reopened.state.study_handoffs[0].personal_notes == "中央塔楼是地标。"
    assert {item.preset_id for item in reopened.state.breakdown_plans} >= {
        "assembly_set",
        "detail_components",
    }
    assert reopened.state.selected_plan_id == details.plan_id
    assert source.read_bytes() == original
    reopened.close()


def test_assets_are_isolated_by_breakdown_plan(tmp_path: Path) -> None:
    source = tmp_path / "scene.png"
    _image(source, (20, 30, 40))
    store = AssetBreakdownStore.create(
        tmp_path / "plans.scenelens-assets",
        "方案隔离",
    )
    main = store.import_image(source, "main")
    first_plan = store.state.breakdown_plans[0]
    second_plan = create_plan_from_preset("detail_components")
    store.add_or_replace_plan(second_plan)
    first_asset = create_manual_asset(
        name="完整塔楼",
        category="building",
        rect=(0.1, 0.1, 0.3, 0.6),
        source_image_id=main.image_id,
        plan_id=first_plan.plan_id,
    )
    second_asset = create_manual_asset(
        name="塔楼窗框",
        category="modular_piece",
        rect=(0.2, 0.2, 0.1, 0.1),
        source_image_id=main.image_id,
        plan_id=second_plan.plan_id,
    )
    store.add_or_replace_asset(first_asset)
    store.add_or_replace_asset(second_asset)
    assert first_asset.plan_id != second_asset.plan_id
    store.delete_plan(second_plan.plan_id)
    assert {item.asset_id for item in store.state.assets} == {
        first_asset.asset_id
    }
    store.close()
