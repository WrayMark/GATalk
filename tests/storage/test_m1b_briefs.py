from __future__ import annotations

import sqlite3
from pathlib import Path

from PIL import Image

from scenelens.storage.atomic import atomic_write_json
from scenelens.storage.migrations import configure_connection
from scenelens.storage.models import (
    MANIFEST_FORMAT,
    MANIFEST_FORMAT_VERSION,
    BriefDocumentType,
    BriefFieldValue,
    FieldSource,
    ProjectManifest,
)
from scenelens.storage.project_store import ProjectStore, utc_now
from scenelens.storage import migrations


def _make_image(path: Path, colour: tuple[int, int, int]) -> None:
    Image.new("RGB", (32, 18), colour).save(path)


def test_user_confirmed_brief_field_is_not_overwritten_by_generated_value(
    tmp_path: Path,
):
    store = ProjectStore.create(tmp_path / "brief.scenelens", "Brief")
    document = store.ensure_creative_intent_document()
    changed = store.save_brief_field(
        document.id,
        "weather",
        BriefFieldValue(
            value="薄雾",
            source=FieldSource.USER_INPUT,
            user_confirmed=True,
        ),
    )

    generated_changed = store.save_brief_field(
        document.id,
        "weather",
        BriefFieldValue(
            value="晴朗",
            source=FieldSource.ALGORITHM_INFERENCE,
            confidence=0.8,
            evidence={"analyzer_id": "future-weather"},
        ),
    )

    assert changed is True
    assert generated_changed is False
    restored = store.list_brief_fields(document.id)["weather"]
    assert restored.value == "薄雾"
    assert restored.source is FieldSource.USER_INPUT
    assert restored.user_confirmed is True


def test_reference_change_stales_previous_visual_brief(tmp_path: Path):
    store = ProjectStore.create(tmp_path / "reference.scenelens", "Reference")
    shot = store.create_shot("Shot")
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    _make_image(first_path, (20, 40, 60))
    _make_image(second_path, (100, 120, 140))

    first_asset = store.import_reference(shot.id, first_path)
    first_document = store.get_reference_visual_brief(shot.id)
    assert first_document is not None
    assert first_document.asset_sha256 == first_asset.sha256

    second_asset = store.import_reference(shot.id, second_path)
    second_document = store.get_reference_visual_brief(shot.id)

    assert second_document is not None
    assert second_document.id != first_document.id
    assert second_document.asset_sha256 == second_asset.sha256
    with sqlite3.connect(store.database_path) as connection:
        previous_status = connection.execute(
            """
            SELECT status FROM visual_review_brief_documents WHERE id = ?
            """,
            (first_document.id,),
        ).fetchone()[0]
    assert previous_status == "stale"


def test_schema_one_migration_preserves_legacy_brief_without_guessing(
    tmp_path: Path,
):
    root = tmp_path / "legacy brief.scenelens"
    root.mkdir()
    for name in ("assets", "artifacts", "exports", "backups"):
        (root / name).mkdir()
    now = utc_now()
    project_id = "legacy-m1a-project"
    manifest = ProjectManifest(
        format=MANIFEST_FORMAT,
        format_version=MANIFEST_FORMAT_VERSION,
        project_id=project_id,
        name="旧项目",
        created_at=now,
        updated_at=now,
        app_version="0.1.0",
        database_schema_version=1,
    )
    atomic_write_json(root / "project.json", manifest.to_dict())
    connection = sqlite3.connect(root / "project.db")
    configure_connection(connection)
    try:
        migrations._migration_1(connection, project_id, now)
        connection.execute(
            """
            UPDATE art_briefs
            SET production_stage = '灯光初版',
                time_weather = '清晨薄雾',
                target_mood = '宁静'
            WHERE project_id = ? AND shot_id IS NULL
            """,
            (project_id,),
        )
        connection.execute(
            """
            INSERT INTO schema_migrations(version, name, applied_at, app_version)
            VALUES (1, 'initial_m1a_schema', ?, '0.1.0')
            """,
            (now,),
        )
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()

    store = ProjectStore.open(root)
    document = store.get_creative_intent_document()

    assert document is not None
    assert document.document_type is BriefDocumentType.CREATIVE_INTENT
    fields = store.list_brief_fields(document.id)
    assert fields["production_stage"].value == "灯光初版"
    assert fields["target_moods"].value == "宁静"
    assert fields["additional_notes"].value == (
        "M1A 时间与天气（未拆分）：清晨薄雾"
    )
    assert fields["additional_notes"].evidence["original_value"] == "清晨薄雾"
    assert len(list((root / "backups").glob("pre-migration_0001_to_0002_*"))) == 1
