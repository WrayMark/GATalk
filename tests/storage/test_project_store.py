from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from scenelens.analysis.models import ImageMeasurements, PaletteColour
from scenelens.storage import atomic as atomic_module
from scenelens.storage import migrations
from scenelens.storage.atomic import atomic_write_json
from scenelens.storage.errors import (
    ProjectFormatError,
    ProjectSaveError,
    ProjectVersionError,
)
from scenelens.storage.models import (
    DATABASE_SCHEMA_VERSION,
    MANIFEST_FORMAT,
    MANIFEST_FORMAT_VERSION,
    ArtBrief,
    CanvasState,
    ProjectManifest,
    WorkspaceState,
)
from scenelens.storage.project_store import ProjectStore, utc_now


def _make_image(path: Path, colour=(45, 90, 135)) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 36), colour).save(path)
    return path.read_bytes()


def test_create_project_writes_hybrid_layout_and_schema(tmp_path: Path):
    root = tmp_path / "中世纪 村庄.scenelens"

    store = ProjectStore.create(root, "中世纪村庄")

    assert store.manifest_path.is_file()
    assert store.database_path.is_file()
    assert (root / "assets").is_dir()
    assert (root / "artifacts").is_dir()
    assert (root / "exports").is_dir()
    assert (root / "backups").is_dir()
    assert store.get_art_brief() == ArtBrief()

    with sqlite3.connect(store.database_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        identity = connection.execute(
            "SELECT id FROM project_identity WHERE singleton = 1"
        ).fetchone()[0]
    assert version == DATABASE_SCHEMA_VERSION
    assert identity == store.manifest.project_id


def test_art_brief_shot_version_assets_and_state_survive_reopen(tmp_path: Path):
    root = tmp_path / "项目 含空格.scenelens"
    source = tmp_path / "输入" / "参考 图.png"
    current = tmp_path / "输入" / "UE 截图.png"
    reference_bytes = _make_image(source)
    current_bytes = _make_image(current, (120, 85, 50))
    store = ProjectStore.create(root, "中世纪村庄")
    brief = ArtBrief(
        scene_type="中世纪村庄",
        production_stage="灯光初版",
        target_style="写实风格化",
        time_weather="清晨薄雾",
        target_mood="安静、略带神秘",
        primary_focus="村口钟楼",
        secondary_focus="远处山脊",
        preserve_content="石墙的轮廓",
        main_issues="焦点不够集中",
        excluded_review="材质细节",
        constraints="仅使用现有资产",
    )
    store.save_art_brief(brief)
    shot = store.create_shot("村口主镜头")
    reference_asset = store.import_reference(shot.id, source)
    version = store.add_version(shot.id, current, name="灯光 v1")
    state = WorkspaceState(
        current_shot_id=shot.id,
        current_version_id=version.id,
        display_mode="grayscale",
        comparison_mode="ab",
        ab_role="current",
        sync_views=False,
        blur_sigma=2.5,
    )
    store.save_workspace_state(state)
    store.save_canvas_state(
        CanvasState("reference", shot.id, None, 1.8, 0.25, 0.7)
    )
    store.save_canvas_state(
        CanvasState("current", shot.id, version.id, 1.8, 0.25, 0.7)
    )
    store.close()

    reopened = ProjectStore.open(root)

    assert reopened.get_art_brief() == brief
    assert reopened.list_shots()[0].reference_asset_id == reference_asset.id
    assert reopened.list_versions(shot.id) == (version,)
    restored = reopened.get_workspace_state()
    assert restored.current_shot_id == shot.id
    assert restored.current_version_id == version.id
    assert restored.display_mode == "grayscale"
    assert restored.comparison_mode == "ab"
    assert restored.blur_sigma == pytest.approx(2.5)
    reference_state = reopened.get_canvas_state("reference", shot.id, None)
    current_state = reopened.get_canvas_state("current", shot.id, version.id)
    assert reference_state is not None
    assert current_state is not None
    assert reference_state.zoom_factor == pytest.approx(1.8)
    assert reference_state.center_x == pytest.approx(0.25)
    assert current_state.zoom_factor == pytest.approx(1.8)

    stored_reference = reopened.asset_path(reference_asset.id)
    stored_current = reopened.asset_path(version.asset_id)
    assert stored_reference.read_bytes() == reference_bytes
    assert stored_current.read_bytes() == current_bytes
    assert reference_asset.sha256 == hashlib.sha256(reference_bytes).hexdigest()
    assert source.read_bytes() == reference_bytes
    assert current.read_bytes() == current_bytes


def test_import_deduplicates_identical_original_bytes(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "dedupe.scenelens", "去重")
    shot = store.create_shot("镜头")
    source = tmp_path / "same.png"
    _make_image(source)

    reference = store.import_reference(shot.id, source)
    version = store.add_version(shot.id, source)

    assert version.asset_id == reference.id
    with sqlite3.connect(store.database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM image_assets").fetchone()[0]
    assert count == 1


def test_measurements_are_restored_and_artifact_is_rebuildable(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "analysis.scenelens", "分析")
    shot = store.create_shot("镜头")
    source = tmp_path / "current.png"
    _make_image(source)
    version = store.add_version(shot.id, source)
    measurements = ImageMeasurements(
        luminance_histogram=np.array([0.25, 0.75], dtype=np.float64),
        palette=(
            PaletteColour(
                rgb=(45, 90, 135),
                oklab=(0.5, -0.02, -0.08),
                proportion=1.0,
            ),
        ),
        sampled_pixel_count=2304,
    )

    store.save_measurements(version.asset_id, measurements)
    store.close()
    reopened = ProjectStore.open(store.root)
    restored = reopened.load_measurements(version.asset_id)

    assert restored is not None
    assert restored.luminance_histogram.tolist() == pytest.approx([0.25, 0.75])
    assert restored.palette == measurements.palette
    artifacts = list(store.artifacts_directory.rglob("measurements.json"))
    assert len(artifacts) == 1
    artifacts[0].unlink()
    assert reopened.load_measurements(version.asset_id) is not None
    assert artifacts[0].is_file()


def test_opening_schema_zero_project_creates_pre_migration_backup(tmp_path: Path):
    root = tmp_path / "旧项目.scenelens"
    root.mkdir()
    for name in ("assets", "artifacts", "exports", "backups"):
        (root / name).mkdir()
    now = utc_now()
    manifest = ProjectManifest(
        format=MANIFEST_FORMAT,
        format_version=MANIFEST_FORMAT_VERSION,
        project_id="legacy-project-id",
        name="旧项目",
        created_at=now,
        updated_at=now,
        app_version="0.0.1",
        database_schema_version=0,
    )
    atomic_write_json(root / "project.json", manifest.to_dict())
    sqlite3.connect(root / "project.db").close()

    store = ProjectStore.open(root)

    assert store.manifest.database_schema_version == DATABASE_SCHEMA_VERSION
    backups = list((root / "backups").glob("pre-migration_*"))
    assert len(backups) == 1
    assert (backups[0] / "project.db").is_file()
    assert (backups[0] / "project.json").is_file()
    assert (backups[0] / "backup.json").is_file()


def test_newer_database_is_never_written(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "future.scenelens", "未来项目")
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION + 1}"
        )
    store.close()

    with pytest.raises(ProjectVersionError):
        ProjectStore.open(store.root)


def test_atomic_manifest_replace_failure_preserves_previous_file(
    tmp_path: Path,
    monkeypatch,
):
    path = tmp_path / "project.json"
    atomic_write_json(path, {"version": 1})
    previous = path.read_bytes()

    def fail_replace(_source, _destination):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(atomic_module.os, "replace", fail_replace)
    with pytest.raises(OSError):
        atomic_write_json(path, {"version": 2})

    assert path.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [path]


def test_manifest_save_failure_keeps_in_memory_and_disk_name(
    tmp_path: Path,
    monkeypatch,
):
    store = ProjectStore.create(tmp_path / "safe.scenelens", "原名称")
    previous_bytes = store.manifest_path.read_bytes()

    def fail_write(_path, _data):
        raise OSError("simulated permission failure")

    monkeypatch.setattr(
        "scenelens.storage.project_store.atomic_write_json",
        fail_write,
    )
    with pytest.raises(ProjectSaveError):
        store.rename_project("新名称")

    assert store.manifest.name == "原名称"
    assert store.manifest_path.read_bytes() == previous_bytes


def test_failed_migration_rolls_back_and_keeps_complete_backup(
    tmp_path: Path,
    monkeypatch,
):
    root = tmp_path / "迁移失败.scenelens"
    root.mkdir()
    for name in ("assets", "artifacts", "exports", "backups"):
        (root / name).mkdir()
    now = utc_now()
    manifest = ProjectManifest(
        format=MANIFEST_FORMAT,
        format_version=MANIFEST_FORMAT_VERSION,
        project_id="migration-failure-id",
        name="迁移失败",
        created_at=now,
        updated_at=now,
        app_version="0.0.1",
        database_schema_version=0,
    )
    atomic_write_json(root / "project.json", manifest.to_dict())
    sqlite3.connect(root / "project.db").close()

    def failing_migration(connection, _project_id, _now):
        connection.execute("CREATE TABLE should_rollback(value TEXT)")
        raise RuntimeError("simulated migration failure")

    monkeypatch.setitem(
        migrations.MIGRATIONS,
        1,
        ("failing_migration", failing_migration),
    )
    with pytest.raises(ProjectFormatError):
        ProjectStore.open(root)

    with sqlite3.connect(root / "project.db") as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'should_rollback'
            """
        ).fetchone()
    assert version == 0
    assert table is None
    backup_records = list((root / "backups").rglob("backup.json"))
    assert len(backup_records) == 1
