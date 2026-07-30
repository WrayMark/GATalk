from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from PIL import Image
import pytest

from scenelens.modules.asset_breakdown.models import (
    AutomaticAssetRun,
    GenerationRecord,
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


def test_v1_asset_project_is_backed_up_before_v2_migration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "migrate.scenelens-assets"
    store = AssetBreakdownStore.create(root, "迁移")
    store.close()
    entry = root / "asset_project.json"
    payload = json.loads(entry.read_text(encoding="utf-8"))
    payload["format_version"] = 1
    payload["module_schema_version"] = 1
    payload["state"].pop("automatic_runs", None)
    entry.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    migrated = AssetBreakdownStore.open(root)
    migrated.close()

    updated = json.loads(entry.read_text(encoding="utf-8"))
    assert updated["format_version"] == 2
    assert updated["module_schema_version"] == 2
    backups = list((root / "backups").glob("asset_project.v1.*.json"))
    assert len(backups) == 1
