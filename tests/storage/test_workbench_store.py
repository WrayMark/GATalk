from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from PIL import Image

from scenelens.core.domain import (
    AIConceptPreview,
    AIConceptPreviewStatus,
    AIRun,
    AIRunStatus,
    Annotation,
    DerivedArtifact,
    Evidence,
    EvidenceSource,
    EvidenceType,
    QualityGate,
    QualityGateState,
    ReviewProfile,
    SourceDocument,
    Task,
    TaskPriority,
    TaskStatus,
)
from scenelens.storage.atomic import atomic_write_json, load_json
from scenelens.storage.project_store import ProjectStore, utc_now
from scenelens.storage.workbench_store import WorkbenchStore


MODULE_ID = "scenelens.visual_review"


def _save_image(path: Path) -> None:
    Image.new("RGB", (32, 24), (80, 100, 120)).save(path)


def test_workbench_entities_round_trip_without_network_or_credentials(
    tmp_path: Path,
):
    project = ProjectStore.create(tmp_path / "共享 核心.scenelens", "共享核心")
    store = WorkbenchStore(project)
    now = utc_now()
    evidence = store.save_evidence(
        Evidence(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            evidence_type=EvidenceType.MEASUREMENT,
            source=EvidenceSource.LOCAL_ANALYZER,
            subject_type="shot",
            subject_id="shot-local",
            payload={"mean_luminance": 0.42},
            created_at=now,
        )
    )
    annotation = store.save_annotation(
        Annotation(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            annotation_type="light_direction",
            geometry={"start": [0.1, 0.2], "end": [0.7, 0.5]},
            label="主光方向候选",
            evidence_id=evidence.id,
            created_at=now,
            updated_at=now,
        )
    )
    task = store.save_task(
        Task(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            title="验证主光方向",
            description="在 UE5 中检查方向光与参考是否一致。",
            priority=TaskPriority.HIGH,
            status=TaskStatus.OPEN,
            source_evidence_id=evidence.id,
            source_annotation_id=annotation.id,
            verification={"method": "导入新截图复查"},
            created_at=now,
            updated_at=now,
        )
    )
    artifact = store.save_artifact(
        DerivedArtifact(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            artifact_type="lighting_luminance_proxy",
            relative_path="artifacts/lighting-proxy.png",
            input_hashes={"current": "abc"},
            parameters={"blur_sigma": 4.0},
            created_at=now,
        )
    )
    run = store.save_ai_run(
        AIRun(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            reviewer_id="lighting_review",
            provider_id="mock",
            model_id="mock-v1",
            capability="vision_review",
            request_hash="request-hash",
            input_manifest={"images": ["current"], "fields": ["intent"]},
            output={"findings": []},
            status=AIRunStatus.COMPLETE,
            created_at=now,
            completed_at=now,
        )
    )
    document = store.save_source_document(
        SourceDocument(
            id=str(uuid.uuid4()),
            module_id=MODULE_ID,
            document_type="review_notes",
            title="灯光记录",
            source_uri="local://notes/lighting",
            content_hash="doc-hash",
            metadata={"language": "zh-CN"},
            created_at=now,
        )
    )
    profile = ReviewProfile(
        id=str(uuid.uuid4()),
        module_id=MODULE_ID,
        name="中世纪村庄门禁",
        reviewer_ids=("art_director_review", "lighting_review"),
        settings={"max_findings": 5},
        created_at=now,
        updated_at=now,
    )
    gate = QualityGate(
        id=str(uuid.uuid4()),
        profile_id=profile.id,
        dimension_id="focus_readability",
        display_name="焦点可读性",
        metric_key="focus.local_contrast",
        operator="gte",
        threshold={"warning": 0.08, "pass": 0.12},
        weight=1.0,
        state=QualityGateState.NOT_EVALUATED,
        updated_at=now,
    )
    store.save_review_profile(profile, (gate,))

    assert store.list_evidence(MODULE_ID) == (evidence,)
    assert store.list_annotations(MODULE_ID) == (annotation,)
    assert store.list_tasks(MODULE_ID) == (task,)
    assert store.update_task_status(task.id, TaskStatus.DONE).status == TaskStatus.DONE
    assert store.get_ai_run(run.id) == run
    assert store.list_ai_runs(run.module_id) == (run,)
    assert store.delete_ai_run(run.id) is True
    assert store.get_ai_run(run.id) is None
    assert store.get_review_profile(profile.id) == (profile, (gate,))
    assert artifact.relative_path.startswith("artifacts/")
    assert document.source_uri.startswith("local://")
    project.close()


def test_ai_run_manifest_rejects_credential_fields(tmp_path: Path):
    project = ProjectStore.create(tmp_path / "密钥保护.scenelens", "密钥保护")
    store = WorkbenchStore(project)
    now = utc_now()
    run = AIRun(
        id=str(uuid.uuid4()),
        module_id=MODULE_ID,
        reviewer_id="lighting_review",
        provider_id="mock",
        model_id="mock-v1",
        capability="vision_review",
        request_hash="request-hash",
        input_manifest={"api_key": "must-not-persist"},
        status=AIRunStatus.PENDING,
        created_at=now,
    )

    with pytest.raises(ValueError, match="credentials"):
        store.save_ai_run(run)
    project.close()


def test_ai_concept_preview_is_artifact_not_version(tmp_path: Path):
    project = ProjectStore.create(
        tmp_path / "预演隔离.scenelens",
        "预演隔离",
    )
    shot = project.create_shot("镜头")
    source = tmp_path / "source.png"
    _save_image(source)
    version = project.add_version(shot.id, source)
    before_versions = project.list_versions(shot.id)
    preview = AIConceptPreview(
        id=str(uuid.uuid4()),
        module_id=MODULE_ID,
        shot_id=shot.id,
        source_version_id=version.id,
        provider_id="mock",
        model_id="mock-image",
        relative_path="artifacts/ai_previews/preview.png",
        input_hashes={"current": "abc"},
        instruction={"edit_mode": "lighting_only"},
        protection_constraints={"preserve_geometry": True},
        validation_metrics={"structure_drift": 0.02},
        preview_status=AIConceptPreviewStatus.CANDIDATE,
        created_at=utc_now(),
    )
    workbench = WorkbenchStore(project)
    workbench.save_ai_concept_preview(preview)
    assert workbench.list_ai_concept_previews(MODULE_ID) == (preview,)
    assert project.list_versions(shot.id) == before_versions
    project.close()


def test_schema_four_migrates_to_workbench_core_with_backup(tmp_path: Path):
    project = ProjectStore.create(tmp_path / "schema4.scenelens", "schema4")
    root = project.root
    project.close()
    tables = (
        "workbench_quality_gates",
        "workbench_review_profiles",
        "workbench_source_documents",
        "workbench_ai_runs",
        "workbench_derived_artifacts",
        "workbench_tasks",
        "workbench_annotations",
        "workbench_evidence",
    )
    with sqlite3.connect(root / "project.db") as connection:
        for table in tables:
            connection.execute(f"DROP TABLE {table}")
        connection.execute(
                "DELETE FROM schema_migrations WHERE version IN (5, 6, 7)"
        )
        connection.execute("PRAGMA user_version = 4")
        connection.commit()
    manifest = load_json(root / "project.json")
    manifest["database"]["schema_version"] = 4
    atomic_write_json(root / "project.json", manifest)

    migrated = ProjectStore.open(root)
    with sqlite3.connect(migrated.database_path) as connection:
        actual = {
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'workbench_%'
                """
            )
        }

    assert actual == set(tables)
    assert len(
        list((root / "backups").glob("pre-migration_0004_to_0007_*"))
    ) == 1
    migrated.close()


def test_schema_five_migrates_lighting_observation_state_with_backup(
    tmp_path: Path,
):
    project = ProjectStore.create(
        tmp_path / "schema5-lighting.scenelens",
        "schema5",
    )
    root = project.root
    project.close()
    with sqlite3.connect(root / "project.db") as connection:
        connection.execute(
            "ALTER TABLE workspace_state DROP COLUMN silhouette_threshold"
        )
        connection.execute(
                "DELETE FROM schema_migrations WHERE version IN (6, 7)"
        )
        connection.execute("PRAGMA user_version = 5")
        connection.commit()
    manifest = load_json(root / "project.json")
    manifest["database"]["schema_version"] = 5
    atomic_write_json(root / "project.json", manifest)

    migrated = ProjectStore.open(root)
    assert migrated.get_workspace_state().silhouette_threshold == 0.45
    migrated.close()
    assert len(
        list((root / "backups").glob("pre-migration_0005_to_0007_*"))
    ) == 1


def test_schema_six_migrates_composition_guide_state_with_backup(
    tmp_path: Path,
):
    project = ProjectStore.create(
        tmp_path / "schema6-composition.scenelens",
        "schema6",
    )
    root = project.root
    project.close()
    with sqlite3.connect(root / "project.db") as connection:
        connection.execute(
            "ALTER TABLE workspace_state DROP COLUMN composition_guide"
        )
        connection.execute(
            "DELETE FROM schema_migrations WHERE version = 7"
        )
        connection.execute("PRAGMA user_version = 6")
        connection.commit()
    manifest = load_json(root / "project.json")
    manifest["database"]["schema_version"] = 6
    atomic_write_json(root / "project.json", manifest)

    migrated = ProjectStore.open(root)
    assert migrated.get_workspace_state().composition_guide == "none"
    migrated.close()
    assert len(
        list((root / "backups").glob("pre-migration_0006_to_0007_*"))
    ) == 1
