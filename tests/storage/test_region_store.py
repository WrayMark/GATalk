from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from PIL import Image

from scenelens.modules.visual_review import MODULE_ID
from scenelens.modules.visual_review.region_store import RegionStore
from scenelens.modules.visual_review.regions import NormalizedRect
from scenelens.storage.atomic import atomic_write_json, load_json
from scenelens.storage.project_store import ProjectStore, utc_now


def _make_image(path: Path, colour: tuple[int, int, int]) -> None:
    Image.new("RGB", (96, 54), colour).save(path)


def _make_project(tmp_path: Path):
    root = tmp_path / "中文 区域项目.scenelens"
    reference_path = tmp_path / "参考 原图.png"
    current_1_path = tmp_path / "当前 截图 1.png"
    current_2_path = tmp_path / "当前 截图 2.png"
    _make_image(reference_path, (60, 90, 130))
    _make_image(current_1_path, (80, 105, 125))
    _make_image(current_2_path, (95, 110, 120))
    project = ProjectStore.create(root, "中世纪村庄")
    shot = project.create_shot("村口主镜头")
    project.import_reference(shot.id, reference_path)
    version_1 = project.add_version(shot.id, current_1_path, "灯光 v1")
    version_2 = project.add_version(shot.id, current_2_path, "灯光 v2")
    return project, shot, version_1, version_2


def test_regions_pairs_and_custom_values_survive_reopen(tmp_path: Path):
    project, shot, version_1, _version_2 = _make_project(tmp_path)
    regions = RegionStore(project)
    reference = regions.create_region(
        shot.id,
        "reference",
        None,
        "远处 钟楼",
        "自定义建筑焦点",
        NormalizedRect(0.15, 0.1, 0.3, 0.5),
    )
    current = regions.create_region(
        shot.id,
        "current",
        version_1.id,
        "UE 钟楼",
        "主体",
        NormalizedRect(0.2, 0.12, 0.28, 0.48),
    )
    pair = regions.create_pair(
        reference.id,
        current.id,
        "钟楼对应",
        "自定义建筑焦点",
        "观察轮廓和亮度层级",
    )
    root = project.root
    project.close()

    reopened = ProjectStore.open(root)
    restored = RegionStore(reopened).list_pair_views(shot.id, version_1.id)

    assert len(restored) == 1
    assert restored[0].pair == pair
    assert restored[0].reference_region.name == "远处 钟楼"
    assert restored[0].reference_region.semantic_type == "自定义建筑焦点"
    assert restored[0].current_region.normalized_rect == NormalizedRect(
        0.2,
        0.12,
        0.28,
        0.48,
    )
    reopened.close()


def test_reference_regions_are_shot_bound_and_current_regions_are_version_bound(
    tmp_path: Path,
):
    project, shot, version_1, version_2 = _make_project(tmp_path)
    regions = RegionStore(project)
    reference = regions.create_region(
        shot.id,
        "reference",
        None,
        "天空",
        "天空",
        NormalizedRect(0.0, 0.0, 1.0, 0.35),
    )
    current = regions.create_region(
        shot.id,
        "current",
        version_1.id,
        "天空 v1",
        "天空",
        NormalizedRect(0.0, 0.0, 1.0, 0.32),
    )
    regions.create_pair(reference.id, current.id, "天空", "天空")

    assert regions.list_pair_views(shot.id, version_2.id) == ()
    assert reference in regions.list_regions(shot.id, version_id=version_2.id)
    assert current not in regions.list_regions(shot.id, version_id=version_2.id)
    project.close()


def test_copy_previous_version_regions_clones_current_side_only(tmp_path: Path):
    project, shot, version_1, version_2 = _make_project(tmp_path)
    regions = RegionStore(project)
    reference = regions.create_region(
        shot.id,
        "reference",
        None,
        "主体参考",
        "主体",
        NormalizedRect(0.25, 0.2, 0.4, 0.6),
    )
    old_current = regions.create_region(
        shot.id,
        "current",
        version_1.id,
        "主体 v1",
        "主体",
        NormalizedRect(0.3, 0.2, 0.38, 0.6),
    )
    old_pair = regions.create_pair(reference.id, old_current.id, "主体", "主体")

    copied = regions.copy_previous_version_regions(
        shot.id,
        version_1.id,
        version_2.id,
    )
    new_view = regions.list_pair_views(shot.id, version_2.id)[0]

    assert len(copied) == 1
    assert copied[0].id != old_pair.id
    assert new_view.reference_region.id == reference.id
    assert new_view.current_region.id != old_current.id
    assert new_view.current_region.version_id == version_2.id

    changed_rect = NormalizedRect(0.35, 0.25, 0.35, 0.55)
    regions.update_region(new_view.current_region.id, rect=changed_rect)
    old_view = regions.list_pair_views(shot.id, version_1.id)[0]

    assert old_view.current_region.normalized_rect == old_current.normalized_rect
    assert regions.get_region(new_view.current_region.id).normalized_rect == changed_rect
    project.close()


def test_region_geometry_change_marks_saved_analysis_stale(tmp_path: Path):
    project, shot, version_1, _version_2 = _make_project(tmp_path)
    regions = RegionStore(project)
    reference = regions.create_region(
        shot.id,
        "reference",
        None,
        "地面参考",
        "地面",
        NormalizedRect(0.0, 0.65, 1.0, 0.35),
    )
    current = regions.create_region(
        shot.id,
        "current",
        version_1.id,
        "地面当前",
        "地面",
        NormalizedRect(0.0, 0.6, 1.0, 0.4),
    )
    pair = regions.create_pair(reference.id, current.id, "地面", "地面")
    now = utc_now()
    with project.module_write_connection(MODULE_ID) as connection:
        connection.execute(
            """
            INSERT INTO visual_review_region_analyses(
                id, pair_id, module_id, analyzer_id, analyzer_version,
                reference_image_hash, current_image_hash,
                reference_region_geometry_json, current_region_geometry_json,
                shared_palette_cache_key, parameters_json, cache_key,
                result_json, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?)
            """,
            (
                str(uuid.uuid4()),
                pair.id,
                MODULE_ID,
                "paired_region_comparison",
                "1",
                "reference-hash",
                "current-hash",
                json.dumps(reference.normalized_rect.to_dict()),
                json.dumps(current.normalized_rect.to_dict()),
                "palette-key",
                "{}",
                "region-analysis-key",
                "{}",
                now,
            ),
        )

    regions.update_region(
        current.id,
        rect=NormalizedRect(0.0, 0.58, 1.0, 0.42),
    )

    assert regions.list_pair_views(shot.id, version_1.id)[0].analysis_status == "stale"
    project.close()


def test_deleting_region_removes_its_pair_but_preserves_other_side(tmp_path: Path):
    project, shot, version_1, _version_2 = _make_project(tmp_path)
    regions = RegionStore(project)
    reference = regions.create_region(
        shot.id,
        "reference",
        None,
        "前景参考",
        "前景",
        NormalizedRect(0.0, 0.55, 0.4, 0.45),
    )
    current = regions.create_region(
        shot.id,
        "current",
        version_1.id,
        "前景当前",
        "前景",
        NormalizedRect(0.0, 0.6, 0.45, 0.4),
    )
    regions.create_pair(reference.id, current.id, "前景", "前景")

    regions.delete_region(current.id)

    assert regions.list_pair_views(shot.id, version_1.id) == ()
    assert regions.get_region(reference.id) == reference
    project.close()


def test_region_analysis_cache_survives_reopen_and_reference_change_stales_it(
    tmp_path: Path,
):
    project, shot, version_1, _version_2 = _make_project(tmp_path)
    regions = RegionStore(project)
    reference = regions.create_region(
        shot.id,
        "reference",
        None,
        "天空参考",
        "天空",
        NormalizedRect(0.0, 0.0, 1.0, 0.4),
    )
    current = regions.create_region(
        shot.id,
        "current",
        version_1.id,
        "天空当前",
        "天空",
        NormalizedRect(0.0, 0.0, 1.0, 0.38),
    )
    pair = regions.create_pair(reference.id, current.id, "天空", "天空")
    reference_asset = project.get_asset(
        project.get_shot(shot.id).reference_asset_id
    )
    current_asset = project.get_asset(version_1.asset_id)
    saved = regions.save_analysis(
        pair.id,
        analyzer_id="paired_region_comparison",
        analyzer_version="1",
        reference_image_hash=reference_asset.sha256,
        current_image_hash=current_asset.sha256,
        reference_region_geometry=reference.normalized_rect.to_dict(),
        current_region_geometry=current.normalized_rect.to_dict(),
        shared_palette_cache_key="shared-palette-key",
        parameters={"low_threshold": 0.3, "high_threshold": 0.7},
        cache_key="paired-analysis-key",
        result={"reference": {"mean": 0.2}, "current": {"mean": 0.3}},
    )
    root = project.root
    project.close()

    reopened = ProjectStore.open(root)
    reopened_regions = RegionStore(reopened)
    restored = reopened_regions.load_analysis("paired-analysis-key")

    assert restored == saved
    replacement = tmp_path / "新 参考.png"
    _make_image(replacement, (150, 100, 60))
    reopened.import_reference(shot.id, replacement)

    assert reopened_regions.load_analysis("paired-analysis-key") is None
    assert reopened_regions.latest_analysis(pair.id).status == "stale"
    reopened.close()


def test_schema_three_migrates_to_four_with_pre_migration_backup(tmp_path: Path):
    project, _shot, _version_1, _version_2 = _make_project(tmp_path)
    root = project.root
    project.close()
    with sqlite3.connect(root / "project.db") as connection:
        for table in (
            "workbench_quality_gates",
            "workbench_review_profiles",
            "workbench_source_documents",
            "workbench_ai_runs",
            "workbench_derived_artifacts",
            "workbench_tasks",
            "workbench_annotations",
            "workbench_evidence",
        ):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("DROP INDEX visual_review_region_analysis_pair")
        connection.execute("DROP TABLE visual_review_region_analyses")
        connection.execute("DROP INDEX visual_review_region_pairs_shot")
        connection.execute("DROP TABLE visual_review_region_pairs")
        connection.execute("DROP INDEX visual_review_regions_selection")
        connection.execute("DROP TABLE visual_review_regions")
        connection.execute(
            """
            UPDATE module_schema_versions SET schema_version = 2
            WHERE module_id = ?
            """,
            (MODULE_ID,),
        )
        connection.execute(
            "DELETE FROM schema_migrations WHERE version IN (4, 5)"
        )
        connection.execute("PRAGMA user_version = 3")
        connection.commit()
    manifest = load_json(root / "project.json")
    manifest["database"]["schema_version"] = 3
    atomic_write_json(root / "project.json", manifest)

    migrated = ProjectStore.open(root)

    with sqlite3.connect(migrated.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'visual_review_region%'
                """
            )
        }
        module_version = connection.execute(
            """
            SELECT schema_version FROM module_schema_versions
            WHERE module_id = ?
            """,
            (MODULE_ID,),
        ).fetchone()[0]
    assert tables == {
        "visual_review_regions",
        "visual_review_region_pairs",
        "visual_review_region_analyses",
    }
    assert module_version == 3
    assert len(list((root / "backups").glob("pre-migration_0003_to_0005_*"))) == 1
    migrated.close()
